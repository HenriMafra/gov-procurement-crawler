import re, json, time, urllib.request, urllib.error
html = open(r"C:\Users\henri\Desktop\COMISSIONAMENTO\index.html", encoding="utf-8").read()
url = re.search(r"SUPABASE_URL\s*=\s*'([^']+)'", html).group(1)
key = re.search(r"SUPABASE_KEY\s*=\s*'([^']+)'", html).group(1)
def read(table, rng="0-9"):
    u=f"{url}/rest/v1/{table}?select=*"
    req=urllib.request.Request(u, headers={"apikey":key,"Authorization":f"Bearer {key}","Prefer":"count=exact","Range":rng})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.headers.get("Content-Range"), json.loads(r.read().decode("utf-8","replace"))
up=False
for i in range(40):  # ~40 * 30s = 20 min
    try:
        read("comissionamentos"); up=True; print("PROJETO NO AR (leitura anon liberada)"); break
    except urllib.error.HTTPError as e:
        up=True; print(f"PROJETO NO AR (respondeu HTTP {e.code}) -> {e.read().decode('utf-8','replace')[:160]}"); break
    except urllib.error.URLError as e:
        print(f"[{i}] ainda subindo ({e.reason})..."); time.sleep(30)
    except Exception as e:
        print(f"[{i}] {type(e).__name__}: {e}"); time.sleep(30)
if up:
    for t in ("comissionamentos","condicionamentos"):
        try:
            cr,data=read(t)
            cols=list(data[0].keys()) if data else "(vazio)"
            print(f"[{t}] OK | Content-Range={cr} | amostra={len(data)} | colunas={cols}")
        except urllib.error.HTTPError as e:
            print(f"[{t}] HTTP {e.code}: {e.read().decode('utf-8','replace')[:200]}")
        except Exception as e:
            print(f"[{t}] {type(e).__name__}: {e}")
print("FIM")
