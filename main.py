import urllib.request
import urllib.error
import json
import ssl
import time
import base64
import hashlib
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
import os

app = FastAPI(
    title="TaskPrime BR",
    description="Automação Sala do Futuro",
    version="2.0.0"
)

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
        if s != 200 or not isinstance(ch, dict) or not ch.get('challenge'):
            return ''
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
        if not isinstance(v, dict) or not v.get('token'):
            return ''
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
    if s != 200 or not isinstance(d, dict) or not d.get('token'):
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
    s2, res = req(f'{BASE}/api/complete_task', method='POST',
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

# ─── MODELS ──────────────────────────────────────────────────────────────────
class LoginBody(BaseModel):
    ra: str
    senha: str
    cf: Optional[str] = None

class TasksBody(BaseModel):
    token: str
    captcha: str
    cf: Optional[str] = None

class CompleteBody(BaseModel):
    token: str
    captcha: Optional[str] = None
    task_id: int
    publication_target: str = ''
    wait_sec: int = 90
    cf: Optional[str] = None
    draft: bool = False

# ─── ROTAS API ───────────────────────────────────────────────────────────────
@app.post('/api/login')
def api_login(body: LoginBody):
    if body.cf and len(body.cf.strip()) < 10:
        body.cf = None
    try:
        return do_login(body.ra, body.senha, body.cf)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/api/tasks')
def api_tasks(body: TasksBody):
    try:
        return do_get_tasks(body.token, body.captcha, body.cf)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/api/complete_task')
def api_complete(body: CompleteBody):
    try:
        return do_complete_task(body.token, body.captcha, body.task_id,
                                body.publication_target, body.wait_sec, body.cf, body.draft)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── FRONTEND ────────────────────────────────────────────────────────
@app.get('/', response_class=HTMLResponse)
def index():
    return HTML_CONTENT

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TaskPrime BR | Automação Sala do Futuro</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdn.jsdelivr.net/npm/font-awesome@4.7.0/css/font-awesome.min.css" rel="stylesheet">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        dark: '#000000',
                        'dark-light': '#050505',
                        'neon-blue': '#00f0ff',
                        'neon-purple': '#b000ff',
                        'neon-green': '#00ff85',
                        'neon-red': '#ff0055',
                    },
                    fontFamily: {
                        rajdhani: ['Rajdhani', 'sans-serif'],
                    },
                    boxShadow: {
                        'neon': '0 0 10px rgba(0, 240, 255, 0.5), 0 0 20px rgba(176, 0, 255, 0.3)',
                        'neon-hover': '0 0 15px rgba(0, 240, 255, 0.7), 0 0 30px rgba(176, 0, 255, 0.5)',
                    }
                }
            }
        }
    </script>
    <style type="text/tailwindcss">
        @layer utilities {
            .content-auto {
                content-visibility: auto;
            }
            .scrollbar-hide {
                -ms-overflow-style: none;
                scrollbar-width: none;
            }
            .scrollbar-hide::-webkit-scrollbar {
                display: none;
            }
            .text-shadow {
                text-shadow: 0 0 8px rgba(0, 240, 255, 0.6);
            }
            .text-shadow-purple {
                text-shadow: 0 0 8px rgba(176, 0, 255, 0.6);
            }
            .bg-gradient-neon {
                background: linear-gradient(135deg, #00f0ff 0%, #b000ff 100%);
            }
            .bg-gradient-neon-rev {
                background: linear-gradient(135deg, #b000ff 0%, #00f0ff 100%);
            }
            .border-gradient {
                border: 1px solid;
                border-image: linear-gradient(135deg, #00f0ff, #b000ff) 1;
            }
            .transition-all-smooth {
                transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            }
            .transform-smooth {
                transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.4s ease;
            }
        }
    </style>
</head>
<body class="bg-dark text-gray-200 font-rajdhani min-h-screen flex flex-col overflow-x-hidden">
    <!-- Background totalmente preto, sem efeitos extras -->
    <div class="fixed inset-0 z-0 bg-dark"></div>

    <!-- Header -->
    <header class="relative z-10 border-b border-gray-900/50 backdrop-blur-md bg-dark/80 transition-all-smooth hover:bg-dark/95">
        <div class="container mx-auto px-4 py-4 flex justify-between items-center">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-gradient-neon flex items-center justify-center shadow-neon transform-smooth hover:scale-105 hover:shadow-neon-hover">
                    <i class="fa fa-rocket text-dark text-lg"></i>
                </div>
                <h1 class="text-2xl font-bold tracking-wider">
                    <span class="text-neon-blue text-shadow">Task</span><span class="text-neon-purple text-shadow-purple">Prime</span> 
                    <span class="text-sm font-normal text-gray-400">BR</span>
                </h1>
            </div>
            <div class="hidden md:block">
                <span class="text-gray-400 text-sm">Desenvolvido por <span class="text-neon-green font-semibold">!richardzs</span></span>
            </div>
        </div>
    </header>

    <!-- Main Content -->
    <main class="relative z-10 container mx-auto px-4 py-8 flex-grow">
        <!-- Login Section -->
        <section id="login-section" class="max-w-md mx-auto transition-all-smooth opacity-100 scale-100">
            <div class="bg-dark-light/90 backdrop-blur-lg rounded-2xl p-8 border border-gray-900/50 shadow-[0_8px_32px_rgba(0,0,0,0.5)] transform-smooth hover:border-neon-blue/20">
                <div class="text-center mb-8">
                    <h2 class="text-[clamp(1.8rem,3vw,2.5rem)] font-bold mb-2 text-white">Acesso ao Sistema</h2>
                    <p class="text-gray-400">Automação completa para Sala do Futuro</p>
                    <div class="mt-2 py-1 px-3 bg-neon-green/10 text-neon-green text-xs rounded-full inline-block">
                        <i class="fa fa-code mr-1"></i> Criado por !richardzs
                    </div>
                </div>

                <form id="login-form" class="space-y-5">
                    <div class="space-y-2">
                        <label class="block text-sm font-medium text-gray-300">RA</label>
                        <div class="relative">
                            <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                <i class="fa fa-id-card text-gray-500"></i>
                            </div>
                            <input type="text" id="ra" class="w-full pl-10 pr-4 py-3 bg-dark border border-gray-800 rounded-lg focus:ring-2 focus:ring-neon-blue/50 focus:border-neon-blue/50 transition-all-smooth outline-none hover:border-gray-700" placeholder="Digite seu RA">
                        </div>
                    </div>

                    <div class="space-y-2">
                        <label class="block text-sm font-medium text-gray-300">Senha</label>
                        <div class="relative">
                            <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                <i class="fa fa-lock text-gray-500"></i>
                            </div>
                            <input type="password" id="senha" class="w-full pl-10 pr-4 py-3 bg-dark border border-gray-800 rounded-lg focus:ring-2 focus:ring-neon-blue/50 focus:border-neon-blue/50 transition-all-smooth outline-none hover:border-gray-700" placeholder="Digite sua senha">
                        </div>
                    </div>

                    <div class="space-y-2">
                        <label class="block text-sm font-medium text-gray-300">Cookie cf_clearance (opcional)</label>
                        <div class="relative">
                            <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                <i class="fa fa-shield text-gray-500"></i>
                            </div>
                            <input type="text" id="cf" class="w-full pl-10 pr-4 py-3 bg-dark border border-gray-800 rounded-lg focus:ring-2 focus:ring-neon-blue/50 focus:border-neon-blue/50 transition-all-smooth outline-none hover:border-gray-700" placeholder="Cole aqui (não obrigatório)">
                        </div>
                    </div>

                    <button type="submit" class="w-full py-3.5 bg-gradient-neon rounded-lg text-dark font-semibold hover:shadow-neon-hover transition-all-smooth transform hover:-translate-y-0.5 active:translate-y-0 hover:scale-[1.02]">
                        <i class="fa fa-sign-in mr-2"></i> ENTRAR NO SISTEMA
                    </button>
                </form>
            </div>
        </section>

        <!-- Dashboard Section -->
        <section id="dashboard-section" class="hidden transition-all-smooth opacity-0 scale-95">
            <div class="mb-8">
                <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">
                    <div>
                        <h2 class="text-[clamp(1.8rem,3vw,2.5rem)] font-bold text-white">Painel de Controle</h2>
                        <p class="text-gray-400" id="user-greeting"></p>
                    </div>
                    <button id="logout-btn" class="px-4 py-2 bg-dark-light border border-gray-800 rounded-lg hover:bg-dark-light/70 transition-all-smooth text-gray-300 hover:border-neon-red/30 hover:text-neon-red">
                        <i class="fa fa-sign-out mr-2"></i> Sair
                    </button>
                </div>

                <!-- Stats Cards -->
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
                    <div class="bg-dark-light/90 backdrop-blur-lg rounded-xl p-5 border border-gray-900/50 hover:border-neon-green/30 transition-all-smooth transform hover:scale-[1.03] hover:shadow-lg">
                        <div class="flex items-start justify-between">
                            <div>
                                <p class="text-gray-400 text-sm mb-1">Atividades Pendentes</p>
                                <h3 id="stat-pending" class="text-4xl font-bold text-neon-green">0</h3>
                            </div>
                            <div class="w-12 h-12 rounded-lg bg-neon-green/10 text-neon-green flex items-center justify-center text-xl transition-all-smooth hover:scale-110">
                                <i class="fa fa-tasks"></i>
                            </div>
                        </div>
                    </div>
                    
                    <div class="bg-dark-light/90 backdrop-blur-lg rounded-xl p-5 border border-gray-900/50 hover:border-neon-blue/30 transition-all-smooth transform hover:scale-[1.03] hover:shadow-lg">
                        <div class="flex items-start justify-between">
                            <div>
                                <p class="text-gray-400 text-sm mb-1">Atividades Concluídas</p>
                                <h3 id="stat-done" class="text-4xl font-bold text-neon-blue">0</h3>
                            </div>
                            <div class="w-12 h-12 rounded-lg bg-neon-blue/10 text-neon-blue flex items-center justify-center text-xl transition-all-smooth hover:scale-110">
                                <i class="fa fa-check-circle"></i>
                            </div>
                        </div>
                    </div>
                    
                    <div class="bg-dark-light/90 backdrop-blur-lg rounded-xl p-5 border border-gray-900/50 hover:border-neon-purple/30 transition-all-smooth transform hover:scale-[1.03] hover:shadow-lg">
                        <div class="flex items-start justify-between">
                            <div>
                                <p class="text-gray-400 text-sm mb-1">Total</p>
                                <h3 id="stat-total" class="text-4xl font-bold text-neon-purple">0</h3>
                            </div>
                            <div class="w-12 h-12 rounded-lg bg-neon-purple/10 text-neon-purple flex items-center justify-center text-xl transition-all-smooth hover:scale-110">
                                <i class="fa fa-database"></i>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Action Buttons -->
                <div class="flex flex-wrap gap-3 mb-8">
                    <button id="btn-fetch" class="px-5 py-2.5 bg-gradient-neon rounded-lg text-dark font-medium hover:shadow-neon transition-all-smooth transform hover:scale-[1.05] active:scale-95">
                        <i class="fa fa-refresh mr-2"></i> BUSCAR ATIVIDADES
                    </button>
                    <button id="btn-select-all" class="px-5 py-2.5 bg-dark-light border border-gray-800 rounded-lg hover:border-neon-blue/40 transition-all-smooth hover:bg-dark-light/60 transform hover:scale-[1.05] active:scale-95">
                        <i class="fa fa-check-square-o mr-2"></i> SELECIONAR TODAS
                    </button>
                    <button id="btn-run-selected" class="px-5 py-2.5 bg-neon-green/10 text-neon-green border border-neon-green/20 rounded-lg hover:bg-neon-green/20 transition-all-smooth transform hover:scale-[1.05] active:scale-95">
                        <i class="fa fa-play mr-2"></i> EXECUTAR SELECIONADAS
                    </button>
                </div>

                <!-- Tasks Sections -->
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <!-- Pending Tasks -->
                    <div id="task-section-pending" class="bg-dark-light/90 backdrop-blur-lg rounded-xl border border-gray-900/50 overflow-hidden transition-all-smooth hover:shadow-lg">
                        <div class="p-4 border-b border-gray-900/50 flex justify-between items-center">
                            <h3 class="font-semibold text-lg text-neon-green flex items-center gap-2">
                                <span class="w-2 h-2 rounded-full bg-neon-green inline-block"></span>
                                Pendentes
                            </h3>
                            <span class="text-sm text-gray-400" id="count-pending">0</span>
                        </div>
                        <ul id="list-pending" class="divide-y divide-gray-900/50 max-h-[500px] overflow-y-auto scrollbar-hide">
                            <li class="p-4 text-center text-gray-500 transition-all-smooth">Nenhuma atividade pendente</li>
                        </ul>
                    </div>

                    <!-- Expired/Done Tasks -->
                    <div id="task-section-expired" class="bg-dark-light/90 backdrop-blur-lg rounded-xl border border-gray-900/50 overflow-hidden transition-all-smooth hover:shadow-lg">
                        <div class="p-4 border-b border-gray-900/50 flex justify-between items-center">
                            <h3 class="font-semibold text-lg text-neon-blue flex items-center gap-2">
                                <span class="w-2 h-2 rounded-full bg-neon-blue inline-block"></span>
                                Concluídas / Expiradas
                            </h3>
                            <span class="text-sm text-gray-400" id="count-expired">0</span>
                        </div>
                        <ul id="list-expired" class="divide-y divide-gray-900/50 max-h-[500px] overflow-y-auto scrollbar-hide">
                            <li class="p-4 text-center text-gray-500 transition-all-smooth">Nenhuma atividade concluída</li>
                        </ul>
                    </div>
                </div>
            </div>
        </section>
    </main>

    <!-- Footer -->
    <footer class="relative z-10 border-t border-gray-900/50 backdrop-blur-md bg-dark/80 py-4 mt-12 transition-all-smooth">
        <div class="container mx-auto px-4 text-center text-gray-500 text-sm">
            <p>© 2026 <span class="text-neon-green">TaskPrime BR</span> • Desenvolvido com ❤️ por <span class="text-neon-blue font-semibold">!richardzs</span></p>
        </div>
    </footer>

    <!-- Notifications -->
    <div id="notification-container" class="fixed top-5 right-5 z-50 space-y-3 transition-all-smooth"></div>

    <!-- Scripts -->
    <script>
        let state = {
            token: null,
            captcha: null,
            cf: null,
            nome: null,
            escola: null,
            tasks: [],
            selected: new Set(),
            running: false
        };

        function notify(message, type = 'info') {
            const container = document.getElementById('notification-container');
            const colors = {
                success: 'bg-neon-green/10 border-neon-green/30 text-neon-green',
                error: 'bg-neon-red/10 border-neon-red/30 text-neon-red',
                info: 'bg-neon-blue/10 border-neon-blue/30 text-neon-blue',
                warning: 'bg-yellow-500/10 border-yellow-500/30 text-yellow-500'
            };
            
            const notif = document.createElement('div');
            notif.className = `max-w-xs p-4 rounded-lg border backdrop-blur-md shadow-lg transition-all-smooth transform translate-x-0 opacity-0 ${colors[type]}`;
            notif.innerHTML = `
                <div class="flex items-start gap-3">
                    <i class="fa ${type === 'success' ? 'fa-check-circle' : type === 'error' ? 'fa-exclamation-circle' : 'fa-info-circle'} text-lg"></i>
                    <div>${message}</div>
                    <button onclick="this.parentElement.parentElement.remove()" class="ml-auto text-gray-400 hover:text-white transition-all-smooth">
                        <i class="fa fa-times"></i>
                    </button>
                </div>
            `;
            
            container.appendChild(notif);
            setTimeout(() => notif.classList.replace('opacity-0', 'opacity-100'), 10);
            setTimeout(() => {
                notif.classList.add('opacity-0', 'translate-x-10');
                setTimeout(() => notif.remove(), 400);
            }, 4000);
        }

        document.getElementById('login-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = e.target.querySelector('button[type="submit"]');
            btn.disabled = true;
            btn.innerHTML = '<i class="fa fa-spinner fa-spin mr-2"></i> PROCESSANDO...';
            
            try {
                const res = await fetch('/api/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        ra: document.getElementById('ra').value.trim(),
                        senha: document.getElementById('senha').value.trim(),
                        cf: document.getElementById('cf').value.trim() || null
                    })
                });
                
                const data = await res.json();
                
                if(!res.ok) throw new Error(data.detail || 'Erro no login');
                
                state.token = data.token;
                state.captcha = data.captcha;
                state.nome = data.nome;
                state.escola = data.escola;
                state.cf = document.getElementById('cf').value.trim() || null;
                
                notify(`Bem-vindo, ${state.nome}!`, 'success');
                
                document.getElementById('login-section').classList.add('opacity-0', 'scale-95');
                setTimeout(() => {
                    document.getElementById('login-section').classList.add('hidden');
                    const dash = document.getElementById('dashboard-section');
                    dash.classList.remove('hidden', 'opacity-0', 'scale-95');
                    dash.classList.add('opacity-100', 'scale-100');
                    document.getElementById('user-greeting').textContent = `${state.nome} • ${state.escola}`;
                }, 400);
                
            } catch(err) {
                notify(err.message, 'error');
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<i class="fa fa-sign-in mr-2"></i> ENTRAR NO SISTEMA';
            }
        });

        async function fetchTasks(){
            try{
                const btnF = document.getElementById('btn-fetch');
                btnF.disabled = true;
                btnF.innerHTML = '<i class="fa fa-spinner fa-spin mr-2"></i> BUSCANDO...';
                
                const r = await fetch('/api/tasks',{
                    method:'POST',headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({token:state.token,captcha:state.captcha,cf:state.cf||null})
                });
                const d=await r.json();
                if(!r.ok){
                    notify('Erro tarefas: '+(d.detail||r.status),'error');
                    btnF.disabled=false;btnF.textContent='BUSCAR ATIVIDADES →';
                    return;
                }
                state.captcha=d.captcha||state.captcha;
                state.tasks=[...d.pending,...d.expired];
                state.selected.clear();

                renderTasks(d.pending,'list-pending');
                renderTasks(d.expired,'list-expired');

                document.getElementById('stat-pending').textContent = d.pending.length;
                document.getElementById('stat-done').textContent = d.expired.length;
                document.getElementById('stat-total').textContent = state.tasks.length;
                document.getElementById('count-pending').textContent = d.pending.length;
                document.getElementById('count-expired').textContent = d.expired.length;

                document.getElementById('task-section-pending').style.display=d.pending.length?'block':'none';
                document.getElementById('task-section-expired').style.display=d.expired.length?'block':'none';

                notify(`${state.tasks.length} atividades encontradas!`, 'success');

                btnF.disabled=false;btnF.textContent='BUSCAR ATIVIDADES →';
            }catch(e){
                notify('Erro: '+e.message,'error');
                const btnF=document.getElementById('btn-fetch');
                btnF.disabled=false;btnF.textContent='BUSCAR ATIVIDADES →';
            }
        }

        function renderTasks(tasks,listId){
            const ul=document.getElementById(listId);
            ul.innerHTML='';
            if(!tasks.length){
                ul.innerHTML='<li class="p-6 text-center text-gray-500 transition-all-smooth">// nenhuma atividade nesta categoria</li>';
                return;
            }
            tasks.forEach(t=>{
                const li=document.createElement('li');
                li.className='p-4 hover:bg-dark-light/70 transition-all-smooth cursor-pointer group border-b border-gray-900/30 last:border-0';
                li.dataset.id=t.id;
                li.innerHTML=`
                <div class="flex items-start gap-3">
                    <div class="w-5 h-5 mt-0.5 rounded border border-gray-700 flex items-center justify-center group-hover:border-neon-blue/50 transition-all-smooth">
                        <i class="fa fa-check text-neon-blue opacity-0 group-[.selected]:opacity-100 transition-all-smooth"></i>
                    </div>
                    <div class="flex-1 min-w-0">
                        <h4 class="font-medium text-gray-200 truncate group-hover:text-white transition-all-smooth">${t.title}</h4>
                        <p class="text-xs text-gray-500 mt-1">ID: ${t.id} • Vencimento: ${t.expire_at || 'Indefinido'}</p>
                    </div>
                    <span class="text-xs px-2 py-0.5 rounded-full transition-all-smooth ${t.tipo==='pendente'?'bg-neon-green/10 text-neon-green':'bg-neon-blue/10 text-neon-blue'}">${t.tipo}</span>
                </div>`;
                li.addEventListener('click',()=>{
                    const id=String(t.id);
                    if(state.selected.has(id)){state.selected.delete(id);li.classList.remove('selected','bg-dark-light/80');}
                    else{state.selected.add(id);li.classList.add('selected','bg-dark-light/80');}
                });
                ul.appendChild(li);
            });
        }

        function selectAll(){
            document.querySelectorAll('#list-pending li, #list-expired li').forEach(li=>{
                if(li.dataset.id){
                    state.selected.add(String(li.dataset.id));
                    li.classList.add('selected','bg-dark-light/80');
                }
            });
            notify(`${state.selected.size} atividades selecionadas`, 'info');
        }

        async function runSelected(){
            if(state.running) return notify('Já há execução em andamento', 'warning');
            if(!state.selected.size) return notify('Nenhuma atividade selecionada', 'warning');
            
            if(!confirm(`Deseja executar ${state.selected.size} atividades?`)) return;
            
            state.running=true;
            notify('Iniciando execução...', 'info');
            
            const ids = Array.from(state.selected);
            
            for(let i=0;i<ids.length;i++){
                const id=ids[i];
                const t=state.tasks.find(x=>String(x.id)===id);
                if(!t) continue;
                
                notify(`Executando ${i+1}/${ids.length}: ${t.title}`, 'info');
                
                try{
                    const r=await fetch('/api/complete_task',{
                        method:'POST',
                        headers:{'Content-Type':'application/json'},
                        body:JSON.stringify({
                            token:state.token,
                            captcha:state.captcha,
                            task_id:t.id,
                            publication_target:t.publication_target,
                            wait_sec:60,
                            cf:state.cf
                        })
                    });
                    const d=await r.json();
                    if(!r.ok) throw new Error(d.detail||'Falha');
                    
                    notify(`✅ Concluído: ${t.title}`, 'success');
                    await new Promise(r=>setTimeout(r,1200));
                }catch(e){
                    notify(`❌ Erro ${t.title}: ${e.message}`, 'error');
                }
            }
            
            state.running=false;
            notify('Execução finalizada!', 'success');
            fetchTasks();
        }

        document.getElementById('btn-fetch').addEventListener('click', fetchTasks);
        document.getElementById('btn-select-all').addEventListener('click', selectAll);
        document.getElementById('btn-run-selected').addEventListener('click', runSelected);
        document.getElementById('logout-btn').addEventListener('click', ()=>location.reload());
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
