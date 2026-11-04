"""Catalogo TMDB italiano: film ancora in sala e uscite dei prossimi 5 mesi. Solo Python standard.

«In sala» = uscita nei cinema italiani (TMDB tipo 2 o 3) negli ultimi IN_THEATRES_DAYS giorni:
TMDB non sa quando un film esce dalle sale, quindi si usa la durata tipica di una programmazione.
Le uscite solo digitali, in DVD/Blu-ray o in TV non contano.
"""
import calendar, datetime as dt, json, os, time, urllib.request, urllib.parse, urllib.error
from pathlib import Path

IN_THEATRES_DAYS = 42
MONTHS_FUTURE = 5
THEATRICAL = (2, 3)  # TMDB: 2 = uscita limitata in sala, 3 = uscita in sala

def shift_month(date, delta):
    month = date.year * 12 + date.month - 1 + delta
    year, month = divmod(month, 12)
    return dt.date(year, month + 1, min(date.day, calendar.monthrange(year, month + 1)[1]))

def bounds(today):
    return today - dt.timedelta(days=IN_THEATRES_DAYS), shift_month(today, MONTHS_FUTURE)

def api(path, params=None):
    params = {"language": "it-IT", **(params or {})}
    token = os.environ.get("TMDB_BEARER_TOKEN", "")
    key = os.environ.get("TMDB_API_KEY", "")
    if not token and not key:
        raise RuntimeError("Configura TMDB_BEARER_TOKEN oppure TMDB_API_KEY nei secret del repository.")
    if key and not token:
        params["api_key"] = key
    request = urllib.request.Request("https://api.themoviedb.org/3/" + path + "?" + urllib.parse.urlencode(params), headers={"Authorization": "Bearer " + token} if token else {})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 4:
                raise RuntimeError(f"TMDB: risposta {error.code}; catalogo precedente conservato.") from None
            time.sleep(min(20, int(error.headers.get("Retry-After", 2 ** (attempt + 1)))))
        except (TimeoutError, urllib.error.URLError):
            if attempt == 4:
                raise RuntimeError("TMDB non raggiungibile; catalogo precedente conservato.") from None
            time.sleep(2 ** attempt)

def italian_theatrical_dates(movie, start, end):
    """Date di uscita nelle sale italiane comprese nella finestra, in ordine."""
    italian = [release for country in movie.get("release_dates", {}).get("results", []) if country.get("iso_3166_1") == "IT"
               for release in country.get("release_dates", []) if release.get("type") in THEATRICAL]
    return sorted({release.get("release_date", "")[:10] for release in italian if start.isoformat() <= release.get("release_date", "")[:10] <= end.isoformat()})

def build(today=None, fetch=api):
    today = today or dt.date.today()
    start, end = bounds(today)
    ids = set()
    current = start
    while current <= end:
        stop = min(end, dt.date(current.year, current.month, calendar.monthrange(current.year, current.month)[1]))
        params = {"region": "IT", "with_release_type": "|".join(map(str, THEATRICAL)), "release_date.gte": current.isoformat(), "release_date.lte": stop.isoformat(), "include_adult": "false"}
        page = 1
        while True:
            data = fetch("discover/movie", {**params, "page": page})
            if int(data.get("total_pages", 0)) > 500:
                raise RuntimeError("Troppi risultati nel mese: interrompo senza pubblicare un catalogo parziale.")
            ids.update(movie["id"] for movie in data.get("results", []))
            if page >= int(data.get("total_pages", 0)):
                break
            page += 1
        current = stop + dt.timedelta(days=1)
    movies = []
    for movie_id in sorted(ids):
        movie = fetch(f"movie/{movie_id}", {"append_to_response": "release_dates,videos"})
        dates = italian_theatrical_dates(movie, start, end)
        if not dates:
            continue
        # In sala se è già uscito nella finestra; altrimenti la prima uscita futura.
        past = [d for d in dates if d <= today.isoformat()]
        release = past[-1] if past else dates[0]
        videos = movie.get("videos", {}).get("results", [])
        youtube = next((v.get("key") for v in videos if v.get("site") == "YouTube" and v.get("type") == "Trailer"), None)
        movies.append({"id": movie_id, "title": movie.get("title", ""), "originalTitle": movie.get("original_title", ""), "releaseDate": release,
                       "status": "inSala" if past else "inArrivo", "overview": movie.get("overview", ""), "posterPath": movie.get("poster_path"),
                       "genreIds": [g["id"] for g in movie.get("genres", [])], "youtubeKey": youtube})
    movies.sort(key=lambda m: (m["releaseDate"], m["title"].casefold()))
    return {"schemaVersion": 2, "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(), "region": "IT", "language": "it-IT",
            "windowStart": start.isoformat(), "windowEnd": end.isoformat(), "inTheatresDays": IN_THEATRES_DAYS, "monthsFuture": MONTHS_FUTURE,
            "count": len(movies), "movies": movies}

if __name__ == "__main__":
    result = build()
    target = Path(os.environ.get("CATALOGUE_OUTPUT", "cinema-it.json"))
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(target)
    in_sala = sum(m["status"] == "inSala" for m in result["movies"])
    print(f"Catalogo: {in_sala} film in sala e {result['count'] - in_sala} in arrivo, {result['windowStart']} – {result['windowEnd']}")
