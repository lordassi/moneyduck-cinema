import os, json, calendar
from datetime import date, datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

TOKEN=os.environ["TMDB_READ_TOKEN"]
BASE_URL="https://api.themoviedb.org/3"

def add_months(d,months):
    m=d.month-1+months; y=d.year+m//12; m=m%12+1
    return date(y,m,min(d.day,calendar.monthrange(y,m)[1]))

def tmdb_get(path,params=None):
    q=urlencode(params or {}); url=f"{BASE_URL}{path}"+(f"?{q}" if q else "")
    req=Request(url,headers={"Authorization":f"Bearer {TOKEN}","Accept":"application/json","User-Agent":"MoneyDuck-Cinema/1.0"})
    with urlopen(req,timeout=25) as r:return json.load(r)

def safe_get(path,params=None):
    try:return tmdb_get(path,params)
    except (HTTPError,URLError,TimeoutError,OSError) as e:
        print("TMDB warning",path,e);return {}

def d10(v):
    try:return date.fromisoformat(str(v or "")[:10])
    except ValueError:return None

def italian_date(movie_id,start,end):
    data=safe_get(f"/movie/{movie_id}/release_dates")
    it=next((x for x in data.get("results",[]) if x.get("iso_3166_1")=="IT"),None)
    if not it:return None
    for typ in (3,2):
        ds=[d10(x.get("release_date")) for x in it.get("release_dates",[]) if int(x.get("type") or 0)==typ]
        ds=[d for d in ds if d and start<=d<=end]
        if ds:return min(ds)
    return None

def trailer_score(v):
    if v.get("site")!="YouTube" or v.get("type")!="Trailer":return -1
    score=100 if v.get("official") is True else 0
    score+=35 if v.get("iso_3166_1")=="IT" else 0
    score+=30 if v.get("iso_639_1")=="it" else 0
    name=str(v.get("name") or "").lower()
    score+=10 if "trailer" in name else 0
    score+=8 if ("ufficial" in name or "official" in name) else 0
    return score

def trailer(movie_id):
    videos=[];seen=set()
    for lang in ("it-IT","en-US"):
        for v in safe_get(f"/movie/{movie_id}/videos",{"language":lang}).get("results",[]):
            k=str(v.get("key") or "").strip()
            if len(k)==11 and k not in seen:seen.add(k);videos.append(v)
    videos=[v for v in videos if trailer_score(v)>=0]
    if not videos:return None
    videos.sort(key=lambda v:(trailer_score(v),str(v.get("published_at") or "")),reverse=True)
    return videos[0].get("key")

today=date.today(); end=add_months(today,3)
params={"language":"it-IT","region":"IT","with_release_type":"3|2","release_date.gte":today.isoformat(),"release_date.lte":end.isoformat(),"include_adult":"false","page":1}
found={};page=1
while True:
    params["page"]=page; data=tmdb_get("/discover/movie",params)
    for m in data.get("results",[]):found[m["id"]]=m
    if page>=min(int(data.get("total_pages",1) or 1),500):break
    page+=1

movies=[];trailers=0
for i,m in enumerate(found.values(),1):
    mid=int(m["id"]); rd=italian_date(mid,today,end)
    if not rd:continue
    yk=trailer(mid); trailers+=bool(yk)
    movies.append({"id":mid,"title":m.get("title") or m.get("original_title"),"originalTitle":m.get("original_title"),"releaseDate":rd.isoformat(),"overview":m.get("overview",""),"posterPath":m.get("poster_path"),"genreIds":m.get("genre_ids",[]),"youtubeKey":yk,"source":"tmdb"})

movies.sort(key=lambda x:(x["releaseDate"],x["title"].lower()))
generated=datetime.now(timezone.utc).isoformat()
out={"generatedAt":generated,"region":"IT","language":"it-IT","windowStart":today.isoformat(),"windowEnd":end.isoformat(),"count":len(movies),"movies":movies}
os.makedirs("public",exist_ok=True)
with open("public/cinema-it.json","w",encoding="utf-8") as f:json.dump(out,f,ensure_ascii=False,indent=2)
with open("public/index.html","w",encoding="utf-8") as f:f.write(f"<!doctype html><meta charset='utf-8'><p>Generato: {generated}</p><p>Finestra: {today} → {end}</p><p>Film: {len(movies)} · trailer: {trailers}</p><a href='cinema-it.json'>cinema-it.json</a>")
with open("public/.nojekyll","w") as f:f.write("")
print("generatedAt:",generated,"film:",len(movies),"trailers:",trailers)
