import os
import json
import calendar
from datetime import date, datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen


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

    with urlopen(request) as response:
        return json.load(response)


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
    f"dal {today} al {end_date}"
)
