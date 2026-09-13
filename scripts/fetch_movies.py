import os
import json
import calendar
from datetime import date, datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


TOKEN = os.environ["TMDB_READ_TOKEN"]

BASE_URL = "https://api.themoviedb.org/3"


def add_months(d, months):
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1

    day = min(
        d.day,
        calendar.monthrange(year, month)[1]
    )

    return date(year, month, day)


def tmdb_get(path, params=None):
    query = urlencode(params or {})

    url = f"{BASE_URL}{path}"

    if query:
        url += f"?{query}"

    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/json"
        }
    )

    with urlopen(request, timeout=20) as response:
        return json.load(response)


def safe_tmdb_get(path, params=None):
    try:
        return tmdb_get(path, params)
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        print(f"TMDB warning {path}: {error}")
        return {}


def trailer_score(video):
    if video.get("site") != "YouTube":
        return -1

    if video.get("type") != "Trailer":
        return -1

    score = 0

    if video.get("official") is True:
        score += 100

    # Preferenza per materiale destinato all'Italia / in italiano.
    if video.get("iso_3166_1") == "IT":
        score += 35

    if video.get("iso_639_1") == "it":
        score += 30

    name = str(video.get("name") or "").lower()

    if "trailer" in name:
        score += 10

    if "ufficial" in name or "official" in name:
        score += 8

    return score


def find_youtube_trailer(movie_id):
    videos = []
    seen_keys = set()

    # TMDB può restituire set diversi in base alla lingua.
    # Li uniamo e poi scegliamo il miglior Trailer YouTube.
    for language in ("it-IT", "en-US"):
        data = safe_tmdb_get(
            f"/movie/{movie_id}/videos",
            {"language": language}
        )

        for video in data.get("results", []):
            key = str(video.get("key") or "").strip()

            if len(key) != 11:
                continue

            if key in seen_keys:
                continue

            seen_keys.add(key)
            videos.append(video)

    candidates = [
        video
        for video in videos
        if trailer_score(video) >= 0
    ]

    if not candidates:
        return None

    candidates.sort(
        key=lambda video: (
            trailer_score(video),
            str(video.get("published_at") or "")
        ),
        reverse=True
    )

    return candidates[0].get("key")


today = date.today()
end_date = add_months(today, 3)


params = {
    "language": "it-IT",
    "region": "IT",

    # Preferisci uscita cinematografica normale;
    # accetta anche limited theatrical.
    "with_release_type": "3|2",

    "release_date.gte": today.isoformat(),
    "release_date.lte": end_date.isoformat(),

    "include_adult": "false",
    "page": 1
}


movies = {}

page = 1

while True:

    params["page"] = page

    data = tmdb_get(
        "/discover/movie",
        params
    )

    for movie in data.get("results", []):

        movie_id = movie["id"]
        release_date = movie.get("release_date")

        if not release_date:
            continue

        movies[movie_id] = {
            "id": movie_id,
            "title": movie.get("title") or movie.get("original_title"),
            "originalTitle": movie.get("original_title"),
            "releaseDate": release_date,
            "overview": movie.get("overview", ""),
            "posterPath": movie.get("poster_path"),
            "genreIds": movie.get("genre_ids", []),
            "source": "tmdb"
        }

    total_pages = data.get("total_pages", 1)

    if page >= total_pages:
        break

    page += 1


movies = sorted(
    movies.values(),
    key=lambda movie: (
        movie["releaseDate"],
        movie["title"].lower()
    )
)


trailers_found = 0

for index, movie in enumerate(movies, start=1):
    youtube_key = find_youtube_trailer(movie["id"])
    movie["youtubeKey"] = youtube_key

    if youtube_key:
        trailers_found += 1

    print(
        f"[{index}/{len(movies)}] "
        f"{movie['title']} · "
        f"{'trailer OK' if youtube_key else 'nessun trailer'}"
    )


output = {
    "generatedAt": datetime.now(timezone.utc).isoformat(),
    "region": "IT",
    "language": "it-IT",
    "windowStart": today.isoformat(),
    "windowEnd": end_date.isoformat(),
    "count": len(movies),
    "movies": movies
}


os.makedirs("public", exist_ok=True)


with open(
    "public/cinema-it.json",
    "w",
    encoding="utf-8"
) as file:

    json.dump(
        output,
        file,
        ensure_ascii=False,
        indent=2
    )


with open(
    "public/index.html",
    "w",
    encoding="utf-8"
) as file:

    file.write(
        '<a href="cinema-it.json">cinema-it.json</a>'
    )


print(
    f"Generati {len(movies)} film "
    f"dal {today} al {end_date} · "
    f"{trailers_found} trailer YouTube"
)
