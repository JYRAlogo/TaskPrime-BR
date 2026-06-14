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
    description="Automação Sala do Futuro | HACKER EDITION",
    version="3.0.0-GOD"
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

# ─── LOGIN ───────────────────────────────────────────────────────────────────
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

# ✅ SUA FUNÇÃO DE BUSCA ORIGINAL
def do_get_tasks(token, captcha, cf=None):
    cookies = {'cf_clearance': cf} if cf else {}
    s, d = req(f'{BASE}/p/https://edusp-api.ip.tv/room/user',
        headers=headers_auth(token, captcha), cookies=cookies)
    targets = []
    if s == 200:
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
        return d2.get('results') or d2.get('tasks') or []
    def fmt(tasks, tipo):
        return [{'id': t.get('id'),
                 'title': t.get('title', f'#{t.get("id")}'),
                 'expire_at': (t.get('expire_at','')[:10] if t.get('expire_at') else '-'),
                 'publication_target': t.get('publication_target',''),
                 'tipo': tipo} for t in tasks]
    return {'pending': fmt(fetch(False), 'pendente'),
            'expired': fmt(fetch(True),  'expirada'),
            'captcha': captcha}

# ✅ SUA FUNÇÃO DE FINALIZAÇÃO ORIGINAL
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

# ─── ROTAS ───────────────────────────────────────────────────────────────
@app.post('/api/login')
def api_login(body: LoginBody):
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

# ─── FRONTEND: TUDO PRETO, SEM UNDERLINES, CRÉDITOS ROXOS + DISCORD ───────
@app.get('/', response_class=HTMLResponse)
def index():
    return HTML_CONTENT

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>TaskPrime BR | Hackers Legion</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdn.jsdelivr.net/npm/font-awesome@4.7.0/css/font-awesome.min.css" rel="stylesheet">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        'hacker-black': '#000000',
                        'hacker-dark': '#050505',
                        'hacker-gray': '#101010',
                        'hacker-light-gray': '#1A1A1A',
                        'hacker-green': '#00FF00',
                        'hacker-purple': '#9933FF',
                        'hacker-purple-bright': '#BB66FF',
                    },
                    fontFamily: {
                        mono: ['JetBrains Mono', 'monospace'],
                    },
                    borderRadius: {
                        'hacker': '32px',
                    }
                }
            }
        }
    </script>
    <style type="text/tailwindcss">
        @layer utilities {
            .content-auto { content-visibility: auto; }
            .scrollbar-hide { -ms-overflow-style: none; scrollbar-width: none; }
            .scrollbar-hide::-webkit-scrollbar { display: none; }
            .backdrop-blur-custom { backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); }
            .transition-all-smooth { transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1); }
            .glow-green { text-shadow: 0 0 10px #00FF00; }
            .glow-purple { text-shadow: 0 0 12px #9933FF; }
            .glow-border { box-shadow: 0 0 15px #00FF0025; }
            .glow-purple-border { box-shadow: 0 0 15px #9933FF30; }
            /* TIRAR TODOS OS UNDERLINES DE LINKS E TEXTOS */
            a, a:hover, a:focus, a:active { text-decoration: none !important; outline: none !important; }
            * { text-decoration: none !important; }
        }
    </style>
</head>
<body class="bg-black text-green-400 font-mono min-h-screen flex flex-col overflow-x-hidden selection:bg-hacker-purple selection:text-black">
    <div class="fixed inset-0 z-0 bg-black"></div>
    <div class="fixed inset-0 z-0 opacity-3 bg-[url('https://grainy-gradients.vercel.app/noise.svg')]"></div>

    <main class="relative z-10 w-full min-h-screen flex items-center justify-center p-4">
        
        <!-- Login -->
        <section id="login-screen" class="w-full max-w-md transition-all-smooth opacity-100 scale-100">
            <div class="bg-black/95 backdrop-blur-custom rounded-hacker border border-green-500/40 shadow-2xl p-7 md:p-9 glow-border">
                <div class="text-center mb-6">
                    <h1 class="text-[clamp(2rem,5vw,2.8rem)] font-black text-green-400 glow-green mb-2 tracking-wider">
                        &lt;/&gt; TASK_PRIME
                    </h1>
                    
                    <!-- SEUS CRÉDITOS EM ROXO / COLORIDO -->
                    <div class="mt-2 mb-4">
                        <p class="text-hacker-purple-bright font-bold text-sm glow-purple tracking-wider">
                            DESENVOLVIDO POR: HACKERS LEGION
                        </p>
                        <a href="https://discord.gg/hackerslegion" target="_blank" class="inline-block mt-1 px-4 py-1 bg-hacker-purple/20 border border-hacker-purple/50 rounded-full text-hacker-purple-bright hover:bg-hacker-purple/40 transition-all-smooth text-xs font-bold glow-purple">
                            <i class="fa fa-discord mr-1"></i> DISCORD: HACKERS LEGION
                        </a>
                    </div>

                    <p class="text-green-500/70 text-sm font-semibold">// AUTOMAÇÃO SALA DO FUTURO //</p>
                </div>

                <form id="login-form" class="space-y-6">
                    <div class="space-y-2">
                        <label class="block text-sm font-bold text-green-300">USUARIO RA</label>
                        <input type="text" id="ra" class="w-full px-5 py-4 bg-black border border-green-600/50 rounded-hacker focus:outline-none focus:border-green-400 text-green-300 placeholder:text-green-700/60 transition-all-smooth" placeholder="DIGITE SEU RA">
                    </div>
                    <div class="space-y-2">
                        <label class="block text-sm font-bold text-green-300">SENHA ACESSO</label>
                        <input type="password" id="senha" class="w-full px-5 py-4 bg-black border border-green-600/50 rounded-hacker focus:outline-none focus:border-green-400 text-green-300 placeholder:text-green-700/60 transition-all-smooth" placeholder="DIGITE SUA SENHA">
                    </div>
                    <div class="space-y-2">
                        <label class="block text-sm font-bold text-green-300">COOKIE CF (OPCIONAL)</label>
                        <input type="text" id="cf" class="w-full px-5 py-4 bg-black border border-green-600/50 rounded-hacker focus:outline-none focus:border-green-400 text-green-300 placeholder:text-green-700/60 transition-all-smooth" placeholder="SE QUISER COLOCAR">
                    </div>

                    <button type="submit" class="w-full py-4 bg-green-500 hover:bg-green-400 text-black font-black rounded-hacker transition-all-smooth glow-border mt-3 tracking-wider uppercase text-lg">
                        EXECUTAR LOGIN
                    </button>
                </form>
            </div>
        </section>

        <!-- Modal Principal -->
        <section id="main-modal" class="hidden w-full max-w-lg transition-all-smooth opacity-0 scale-95">
            <div class="bg-black/95 backdrop-blur-custom rounded-hacker border border-green-500/40 shadow-2xl overflow-hidden glow-border">
                
                <!-- Cabeçalho -->
                <div class="flex items-center justify-between p-6 border-b border-green-600/40 bg-green-900/10">
                    <div>
                        <h2 class="text-xl font-black text-green-400 glow-green tracking-wider">PAINEL DE CONTROLE</h2>
                        <p class="text-hacker-purple-bright text-xs font-bold glow-purple mt-1">HACKERS LEGION</p>
                    </div>
                    <button id="btn-close" class="text-green-500 hover:text-green-300 text-2xl transition-all-smooth">
                        <i class="fa fa-times-circle"></i>
                    </button>
                </div>

                <!-- Lista -->
                <div class="p-6 max-h-[65vh] overflow-y-auto scrollbar-hide bg-black">
                    <label class="flex items-center gap-3 mb-7 text-green-300 font-bold cursor-pointer text-lg">
                        <input type="checkbox" id="select-all" class="w-5 h-5 accent-green-500 rounded-sm">
                        <span>SELECIONAR TODOS</span>
                    </label>

                    <div id="tasks-list" class="space-y-4 mb-7">
                        <div class="text-center text-green-700/70 py-8 font-bold text-lg tracking-wider">AGUARDANDO COMANDO... <br><br> [ CLICAR: BUSCAR ATIVIDADES ]</div>
                    </div>

                    <p class="text-xs text-green-600/60 mb-7 italic font-medium">
                        * TEMPO DE EXECUÇÃO BASEADO NO MÍNIMO DA ATIVIDADE
                    </p>

                    <!-- Tempo -->
                    <div class="grid grid-cols-2 gap-6 mb-3">
                        <div class="space-y-2">
                            <label class="block text-sm font-bold text-green-400">TEMPO MIN (MIN)</label>
                            <input type="number" id="min-time" value="1" min="1" class="w-full px-4 py-3 bg-black border border-green-600/50 rounded-hacker text-center text-green-300 font-bold focus:outline-none">
                        </div>
                        <div class="space-y-2">
                            <label class="block text-sm font-bold text-green-400">TEMPO MAX (MIN)</label>
                            <input type="number" id="max-time" value="3" min="1" class="w-full px-4 py-3 bg-black border border-green-600/50 rounded-hacker text-center text-green-300 font-bold focus:outline-none">
                        </div>
                    </div>
                </div>

                <!-- Botões -->
                <div class="p-6 border-t border-green-600/40 bg-green-900/10 space-y-4">
                    <button id="btn-run" class="w-full py-4 bg-green-500 hover:bg-green-400 text-black font-black rounded-hacker transition-all-smooth glow-border tracking-wider uppercase text-lg">
                        EXECUTAR SELECIONADAS
                    </button>
                    <button id="btn-draft" class="w-full py-3 bg-black border border-green-800/60 text-green-700/50 rounded-hacker cursor-not-allowed font-bold tracking-wider uppercase">
                        SALVAR RASCUNHO [OFFLINE]
                    </button>
                    <button id="btn-refresh" class="w-full py-3 bg-black hover:bg-hacker-gray text-green-400 rounded-hacker transition-all-smooth text-base font-bold border border-green-700/40 tracking-wider uppercase">
                        <i class="fa fa-refresh mr-2"></i> BUSCAR ATIVIDADES
                    </button>

                    <!-- SEUS CRÉDITOS NO RODAPÉ -->
                    <div class="mt-4 text-center">
                        <a href="https://discord.gg/hackerslegion" target="_blank" class="text-hacker-purple-bright text-sm font-bold glow-purple hover:text-hacker-purple transition-all-smooth">
                            <i class="fa fa-discord mr-1"></i> DISCORD: HACKERS LEGION
                        </a>
                    </div>
                </div>
            </div>
        </section>

    </main>

    <!-- Notificações -->
    <div id="notifications" class="fixed top-6 right-6 z-50 space-y-4 w-full max-w-xs"></div>

    <script>
        let state = { token: null, captcha: null, cf: null, tasks: [], running: false };

        function notify(msg, type='info'){
            const cont = document.getElementById('notifications');
            const colors = {
                success: 'bg-green-900/90 border-green-400 text-green-200 glow-green',
                error: 'bg-red-900/90 border-red-400 text-red-200 glow-red-border',
                info: 'bg-hacker-purple/90 border-hacker-purple text-hacker-purple-bright glow-purple'
            };
            const el = document.createElement('div');
            el.className = `p-5 rounded-hacker border backdrop-blur-custom transition-all-smooth translate-x-0 opacity-0 font-bold tracking-wider ${colors[type]}`;
            el.innerHTML = `<div class="flex items-start gap-3"><i class="fa ${type==='success'?'fa-check-circle':'fa-exclamation-triangle'} text-xl"></i><span>${msg}</span></div>`;
            cont.appendChild(el);
            setTimeout(()=>el.classList.replace('opacity-0','opacity-100'),10);
            setTimeout(()=>{el.classList.add('opacity-0','translate-x-4');setTimeout(()=>el.remove(),300)},4000);
        }

        // Login
        document.getElementById('login-form').addEventListener('submit', async e=>{
            e.preventDefault();
            const btn = e.target.querySelector('button');
            btn.disabled=true; 
            btn.innerHTML='<i class="fa fa-spinner fa-spin mr-2"></i> PROCESSANDO...';
            try{
                const res = await fetch('/api/login',{
                    method:'POST',
                    headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({
                        ra:document.getElementById('ra').value.trim(),
                        senha:document.getElementById('senha').value.trim(),
                        cf:document.getElementById('cf').value.trim()||null
                    })
                });
                const d=await res.json();
                if(!res.ok) throw new Error(d.detail);

                state.token=d.token;
                state.captcha=d.captcha;
                state.cf=document.getElementById('cf').value.trim()||null;

                notify(`ACESSO PERMITIDO: ${d.nome.toUpperCase()}`,'success');
                
                document.getElementById('login-screen').classList.add('opacity-0','scale-95');
                setTimeout(()=>{
                    document.getElementById('login-screen').classList.add('hidden');
                    const mod = document.getElementById('main-modal');
                    mod.classList.remove('hidden','opacity-0','scale-95');
                    mod.classList.add('opacity-100','scale-100');
                },300);

            }catch(err){
                notify(`ERRO: ${err.message}`,'error');
            }finally{
                btn.disabled=false; btn.innerHTML='EXECUTAR LOGIN';
            }
        });

        // Buscar tarefas
        document.getElementById('btn-refresh').addEventListener('click', async ()=>{
            try{
                notify('SOLICITANDO DADOS...','info');
                const res = await fetch('/api/tasks',{
                    method:'POST',
                    headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({token:state.token,captcha:state.captcha,cf:state.cf})
                });
                const d=await res.json();
                if(!res.ok) throw new Error(d.detail);

                state.tasks=[...d.pending,...d.expired];
                state.captcha=d.captcha;
                renderTasks(state.tasks);
                
                if(state.tasks.length === 0){
                    notify('NENHUMA ATIVIDADE ENCONTRADA','info');
                } else {
                    notify(`SUCESSO: ${d.pending.length} ATIVAS | ${d.expired.length} CONCLUÍDAS`,'success');
                }

            }catch(err){
                notify(`FALHA: ${err.message}`,'error');
            }
        });

        function renderTasks(list){
            const el = document.getElementById('tasks-list');
            el.innerHTML='';
            if(!list.length){el.innerHTML='<div class="text-center text-red-500/70 py-6 font-bold">VAZIO</div>';return;}
            
            list.forEach((t, i)=>{
                const div=document.createElement('div');
                div.className='flex items-center justify-between gap-2 p-3 hover:bg-green-900/20 rounded-hacker transition-all-smooth border border-green-800/40 bg-black';
                div.dataset.id=t.id;
                div.dataset.target=t.publication_target;
                div.innerHTML=`
                    <label class="flex items-center gap-3 flex-1 cursor-pointer">
                        <input type="checkbox" class="task-checkbox w-4 h-4 accent-green-500 rounded-sm">
                        <span class="text-sm text-green-300 line-clamp-1">TASK ${i+1}: ${t.title}</span>
                    </label>
                    <span class="text-xs ${t.tipo==='pendente'?'text-green-400':'text-blue-400'} font-bold">${t.tipo.toUpperCase()}</span>
                `;
                el.appendChild(div);
            });

            document.getElementById('select-all').onchange=e=>{
                document.querySelectorAll('.task-checkbox').forEach(cb=>cb.checked=e.target.checked);
            };
        }

        // Executar
        document.getElementById('btn-run').addEventListener('click', async ()=>{
            if(state.running) return notify('PROCESSO ATIVO','info');
            
            const selecionadas=[];
            document.querySelectorAll('#tasks-list > div').forEach(div=>{
                const cb=div.querySelector('.task-checkbox');
                if(cb.checked){
                    selecionadas.push({
                        id:div.dataset.id,
                        target:div.dataset.target
                    });
                }
            });

            if(!selecionadas.length) return notify('NENHUMA TASK SELECIONADA','error');

            const minT=parseInt(document.getElementById('min-time').value);
            const maxT=parseInt(document.getElementById('max-time').value);

            if(minT>maxT) return notify('TEMPO INVALIDO','error');

            if(!confirm(`INICIAR: ${selecionadas.length} TAREFAS?`)) return;

            state.running=true;
            notify('INICIANDO...','info');

            for(let i=0;i<selecionadas.length;i++){
                const atv=selecionadas[i];
                const tempo=Math.floor(Math.random()*(maxT-minT+1))+minT;

                notify(`EXECUTANDO [${i+1}/${selecionadas.length}]`,'info');

                try{
                    const res=await fetch('/api/complete_task',{
                        method:'POST',
                        headers:{'Content-Type':'application/json'},
                        body:JSON.stringify({
                            token:state.token,
                            captcha:state.captcha,
                            task_id:parseInt(atv.id),
                            publication_target:atv.target,
                            wait_sec:tempo,
                            cf:state.cf
                        })
                    });
                    const d=await res.json();
                    if(!res.ok) throw new Error(d.detail);

                    notify(`SUCESSO [${i+1}] | TEMPO: ${d.wait}s`,'success');
                    await new Promise(r=>setTimeout(r,800));

                }catch(err){
                    notify(`FALHA [${i+1}]: ${err.message}`,'error');
                    await new Promise(r=>setTimeout(r,500));
                }
            }

            state.running=false;
            notify('FINALIZADO','success');
        });

        document.getElementById('btn-close').onclick=()=>location.reload();
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
