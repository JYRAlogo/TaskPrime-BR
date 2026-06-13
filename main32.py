import urllib.request
import urllib.error
import json
import ssl
import time
import base64
import hashlib

# ==================================================
#                TASKPRIME BR - by: !richardzs
# ==================================================

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

BASE = 'https://taskitos.cupiditys.lol'
OCP_KEY = 'd701a2043aa24d7ebb37e9adf60d043b'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36'

# ─── HTTP UTILS ──────────────────────────────────────────────────────────────
def req(url, method='GET', data=None, headers={}, cookies={}):
    body = json.dumps(data).encode() if data else None
    h = dict(headers)
    if cookies:
        h['cookie'] = '; '.join(f'{k}={v}' for k, v in cookies.items())
    r = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, context=ctx, timeout=30) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as e:
        try:    return e.code, json.loads(e.read())
        except: return e.code, {}
    except Exception as e:
        return 0, {}

def headers_auth(token, captcha=None):
    h = {
        'accept': '*/*',
        'accept-language': 'pt-BR,pt;q=0.9,en;q=0.8',
        'content-type': 'application/json',
        'x-api-key': token,
        'x-api-platform': 'webclient',
        'x-api-realm': 'edusp',
        'origin': BASE,
        'referer': BASE + '/',
        'user-agent': UA,
    }
    if captcha:
        h['x-captcha-token'] = captcha
    return h

# ─── CAPTCHA ─────────────────────────────────────────────────────────────────
def solve_captcha(cookies={}):
    try:
        s, ch = req(f'{BASE}/captcha/challenge',
            headers={'accept':'*/*','origin':BASE,'referer':BASE+'/','user-agent':UA},
            cookies=cookies)
        if s != 200 or not ch.get('challenge'):
            raise Exception(f'captcha challenge falhou: {ch}')
        t0 = time.time()
        n  = 0
        while hashlib.sha256(f'{ch["salt"]}{n}'.encode()).hexdigest() != ch['challenge']:
            n += 1
        took = int((time.time() - t0) * 1000)
        payload = base64.b64encode(json.dumps({
            'algorithm': ch.get('algorithm', 'SHA-256'),
            'challenge': ch['challenge'], 'number': n,
            'salt': ch['salt'], 'signature': ch['signature'], 'took': took,
        }, separators=(',',':')).encode()).decode()
        s2, v = req(f'{BASE}/captcha/verify', method='POST',
            data={'payload': payload},
            headers={'accept':'*/*','content-type':'application/json',
                     'origin':BASE,'referer':BASE+'/','user-agent':UA},
            cookies=cookies)
        if not v.get('token'):
            raise Exception(f'captcha verify falhou: {v}')
        return v['token']
    except:
        return ''

# ─── LÓGICA ──────────────────────────────────────────────────────────────────
def do_login(ra, senha, cf=None):
    cookies = {'cf_clearance': cf} if cf else {}
    captcha = solve_captcha(cookies)
    s, d = req(
        f'{BASE}/p/https://sedintegracoes.educacao.sp.gov.br/saladofuturobffapi/credenciais/api/LoginCompletoToken',
        method='POST', data={'user': ra, 'senha': senha},
        headers={
            'accept':'*/*','accept-language':'pt-BR,pt;q=0.9',
            'content-type':'application/json',
            'ocp-apim-subscription-key': OCP_KEY,
            'x-captcha-token': captcha,
            'origin': BASE, 'referer': BASE+'/', 'user-agent': UA,
        },
        cookies=cookies,
    )
    if s != 200 or not d.get('token'):
        raise Exception(d.get('message') or f'Login falhou ({s})')
    sed_token = d['token']
    nome = ''
    escola = ''
    try:
        p = sed_token.split('.')[1]; p += '=' * (4 - len(p) % 4)
        payload_data = json.loads(base64.b64decode(p))
        nome = payload_data.get('NAME', '').title()
        escola = payload_data.get('SCHOOL_NAME', '') or payload_data.get('SCHOOL', '') or 'EE Sala do Futuro'
    except: pass
    for _ in range(5):
        cap2 = solve_captcha(cookies)
        s2, d2 = req(
            f'{BASE}/p/https://edusp-api.ip.tv/registration/edusp/token',
            method='POST', data={'token': sed_token},
            headers={
                'accept':'*/*','accept-language':'pt-BR,pt;q=0.9,en;q=0.8',
                'content-type':'application/json',
                'x-api-platform':'webclient','x-api-realm':'edusp',
                'x-captcha-token': cap2,
                'origin': BASE,'referer': BASE+'/','priority':'u=1, i',
                'user-agent': UA,
            },
            cookies=cookies,
        )
        tok = ''
        if isinstance(d2, dict):
            tok = d2.get('auth_token') or d2.get('token')
        if s2 == 200 and tok:
            return {'token': tok, 'nome': nome, 'escola': escola, 'captcha': cap2, 'cookies': cookies}
        time.sleep(2)
    raise Exception('Falha ao trocar token após 5 tentativas')

def do_get_tasks(token, captcha, cf=None):
    cookies = {'cf_clearance': cf} if cf else {}
    
    # Pegar todas as salas/grupos
    s, d = req(f'{BASE}/p/https://edusp-api.ip.tv/room/user',
        headers=headers_auth(token, captcha), cookies=cookies)
    targets = []
    if s == 200 and isinstance(d, dict):
        for room in d.get('rooms', []):
            v = room.get('name')
            if v and str(v) not in targets: targets.append(str(v))
            for gc in room.get('group_categories', []):
                v2 = gc.get('id')
                if v2 and str(v2) not in targets: targets.append(str(v2))

    def fetch(expired):
        filter_exp = 'false' if expired else 'true'
        url = (f'{BASE}/p/https://edusp-api.ip.tv/tms/task/todo'
               f'?expired_only={str(expired).lower()}&limit=100&offset=0'
               f'&filter_expired={filter_exp}&is_exam=false&with_answer=true&is_essay=false'
               f'&answer_statuses=draft&answer_statuses=pending&with_apply_moment=true')
        for t in targets: url += f'&publication_target={t}'
        s2, d2 = req(url, headers=headers_auth(token, captcha), cookies=cookies)
        if isinstance(d2, list): return d2
        if isinstance(d2, dict):
            return d2.get('results') or d2.get('tasks') or []
        return []

    def fmt(tasks, tipo):
        lista = []
        if isinstance(tasks, list):
            for t in tasks:
                if isinstance(t, dict):
                    lista.append({
                        'id': t.get('id'),
                        'title': t.get('title', f'#{t.get("id")}'),
                        'expire_at': (t.get('expire_at','')[:10] if t.get('expire_at') else '-'),
                        'publication_target': t.get('publication_target',''),
                        'tipo': tipo
                    })
        return lista

    return {'pending': fmt(fetch(False), 'pendente'),
            'expired': fmt(fetch(True),  'expirada'),
            'captcha': captcha}

def do_complete_task(token, captcha, task_id, publication_target, wait_sec, cf=None, draft=False):
    cookies = {'cf_clearance': cf} if cf else {}
    cap = solve_captcha(cookies)
    s, lesson = req(
        f'{BASE}/p/https://edusp-api.ip.tv/tms/task/{task_id}/apply/?preview_mode=false&room_code={publication_target}',
        headers=headers_auth(token, cap), cookies=cookies)
    if s not in (200, 304):
        raise Exception(f'apply falhou {s}: {lesson.get("message") or lesson}')
    wait = max(lesson.get('min_execution_time') or 60, wait_sec)
    time.sleep(wait)
    cap2 = solve_captcha(cookies)
    s2, res = req(f'{BASE}/api/complete', method='POST',
        data={
            'x_auth_key': token, 'room_code': publication_target,
            'lesson_id': task_id, 'draft': draft, 'lesson_info': lesson,
            'time_spent': wait, 'answer_id': lesson.get('answer_id') or 0,
            'target_score': 100, 'captchaToken': cap2,
        },
        headers={
            'accept':'*/*','accept-language':'pt-BR,pt;q=0.7',
            'content-type':'application/json',
            'origin': BASE,'referer': BASE+'/','priority':'u=1, i',
            'user-agent': UA,
        },
        cookies=cookies)
    if s2 == 200:
        return {'success': True, 'wait': wait, 'draft': draft}
    raise Exception(f'complete falhou {s2}: {res.get("message") or res.get("error") or res}')

# ─── PROGRAMA PRINCIPAL ────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("🚀 TASKPRIME BR - by: !richardzs")
    print("💡 Versão baseada no seu script original que funciona!")
    print("=" * 60)

    try:
        # Entrada do usuário
        ra = input("👉 Digite seu RA: ").strip()
        senha = input("👉 Digite sua senha: ").strip()
        cf = input("👉 Cole o cookie cf_clearance: ").strip()

        if not ra or not senha or not cf:
            print("❌ Preencha todos os campos!")
            exit()

        # Login
        print("\n🔄 Fazendo login...")
        usuario = do_login(ra, senha, cf)
        print(f"✅ Logado como: {usuario['nome']} | {usuario['escola']}")

        # Buscar tarefas
        print("\n🔄 Buscando atividades...")
        resultado = do_get_tasks(usuario['token'], usuario['captcha'], cf)
        pendentes = resultado.get('pending', [])
        expiradas = resultado.get('expired', [])

        print(f"\n📋 Pendentes: {len(pendentes)} | Expiradas: {len(expiradas)}")

        # Mostrar lista
        if pendentes:
            print("\n📌 LISTA DE ATIVIDADES ENCONTRADAS:")
            for i, t in enumerate(pendentes, 1):
                print(f"  {i}. ID:{t['id']} | {t['title']} | 📅 Vence: {t['expire_at']}")

            # Executar primeira
            opc = input("\n▶️ Quer executar a PRIMEIRA atividade? (s/n): ").lower().strip()
            if opc == 's':
                primeira = pendentes[0]
                print(f"\n⏳ Executando: {primeira['title']}...")
                try:
                    ok = do_complete_task(
                        usuario['token'],
                        usuario['captcha'],
                        primeira['id'],
                        primeira['publication_target'],
                        wait_sec=60,
                        cf=cf
                    )
                    print("✅ CONCLUÍDO COM SUCESSO!")
                except Exception as e:
                    print(f"❌ ERRO AO EXECUTAR: {str(e)}")

        else:
            print("\n❌ Nenhuma atividade pendente encontrada.")
            print("💡 Agora está com a lógica exata do seu script original.")

    except Exception as e:
        print(f"\n❌ ERRO GERAL: {str(e)}")

    input("\n🔴 Aperte ENTER para sair...")