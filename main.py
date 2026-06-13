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
    title="TASK PRIME LEGION",
    description="Automação Sala do Futuro | HACKER LEGION",
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

# ─── LÓGICA DE BUSCA = IGUAL AO SEU CÓDIGO ANTIGO QUE FUNCIONAVA 100% ────────
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

# ✅ FUNÇÃO DE BUSCA EXATA DO SEU CÓDIGO QUE DAVA CERTO
def do_get_tasks(token, captcha, cf=None):
    cookies = {'cf_clearance': cf} if cf else {}
    
    targets = []
    try:
        s, d = req(f'{BASE}/p/https://edusp-api.ip.tv/room/user',
            headers=headers_auth(token, captcha), cookies=cookies)
        if s == 200 and isinstance(d, dict):
            for room in d.get('rooms', []):
                room_code = room.get('code') or room.get('name') or room.get('id')
                if room_code and str(room_code) not in targets:
                    targets.append(str(room_code))
                for cat in room.get('group_categories', []):
                    cat_id = cat.get('id') or cat.get('code')
                    if cat_id and str(cat_id) not in targets:
                        targets.append(str(cat_id))
    except:
        pass

    if not targets:
        targets = ["all", "public", "0"]

    def fetch(expired):
        filter_exp = 'false' if expired else 'true'
        url = (f'{BASE}/p/https://edusp-api.ip.tv/tms/task/todo'
               f'?expired_only={str(expired).lower()}'
               f'&limit=500&offset=0'
               f'&filter_expired={filter_exp}'
               f'&is_exam=false&with_answer=true&is_essay=false'
               f'&answer_statuses=draft&answer_statuses=pending'
               f'&with_apply_moment=true&status=published&status=in_progress')
        
        for t in targets:
            url += f'&publication_target={t}'

        try:
            s2, d2 = req(url, headers=headers_auth(token, captcha), cookies=cookies)
            tasks_list = []
            if isinstance(d2, list):
                tasks_list = d2
            elif isinstance(d2, dict):
                if 'results' in d2: tasks_list = d2['results']
                elif 'tasks' in d2: tasks_list = d2['tasks']
                elif 'data' in d2: tasks_list = d2['data']
                elif 'items' in d2: tasks_list = d2['items']
            
            unique = []
            ids = set()
            for t in tasks_list:
                if isinstance(t, dict) and t.get('id') and t['id'] not in ids:
                    ids.add(t['id'])
                    unique.append(t)
            return unique

        except:
            return []

    def fmt(tasks, tipo):
        lista = []
        if isinstance(tasks, list):
            for t in tasks:
                if isinstance(t, dict):
                    lista.append({
                        'id': t.get('id'),
                        'title': t.get('title', f'Atividade #{t.get("id", "0")}'),
                        'expire_at': (t.get('expire_at','')[:10] if t.get('expire_at') else 'Sem prazo'),
                        'publication_target': t.get('publication_target',''),
                        'tipo': tipo,
                        'status': t.get('status', 'desconhecido')
                    })
        return lista

    pendentes = fmt(fetch(False), 'pendente')
    expiradas = fmt(fetch(True), 'expirada/concluída')

    return {'pending': pendentes, 'expired': expiradas, 'captcha': captcha}

# ✅ CORRIGIDO: SEM ERRO 404/500 AO FINALIZAR
def do_complete_task(token, captcha, task_id, publication_target, wait_sec, cf=None, draft=False, score=100):
    cookies = {'cf_clearance': cf} if cf else {}
    cap = solve_captcha(cookies)
    
    s, lesson = req(
        f'{BASE}/p/https://edusp-api.ip.tv/tms/task/{task_id}/apply/?preview_mode=false&room_code={publication_target}',
        headers=headers_auth(token, cap), cookies=cookies)
    if s not in (200, 304):
        raise Exception(f'Erro ao carregar atividade: {s}')
    
    wait = max(lesson.get('min_execution_time') or 60, wait_sec)
    time.sleep(wait)
    
    cap2 = solve_captcha(cookies)
    payload = {
        "task_id": task_id,
        "answer_id": lesson.get('answer_id') or 0,
        "room_code": publication_target,
        "time_spent": wait,
        "score": score,
        "draft": draft,
        "captcha_token": cap2
    }

    s2, res = req(
        f'{BASE}/p/https://edusp-api.ip.tv/tms/task/{task_id}/answer',
        method='POST',
        data=payload,
        headers=headers_auth(token, cap2),
        cookies=cookies
    )

    if s2 in (200, 201, 304):
        return {'success': True}
    raise Exception(f'Falha: {s2} - {res}')

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
    wait_sec: int = 2
    cf: Optional[str] = None
    draft: bool = False
    score: int = 100

# ─── ROTAS ───────────────────────────────────────────────────────────────
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
        resultado = do_get_tasks(body.token, body.captcha, body.cf)
        return resultado
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/api/complete_task')
def api_complete(body: CompleteBody):
    try:
        return do_complete_task(
            body.token, body.captcha, body.task_id,
            body.publication_target, body.wait_sec,
            body.cf, body.draft, body.score
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── FRONTEND: ESTILO HACKER + BORDAS REDONDAS + TUDO PRETO ─────────────────
@app.get('/', response_class=HTMLResponse)
def index():
    return HTML_CONTENT

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>TaskPrime BR </> HACKER MODE</title>
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
                        'hacker-dark': '#0A0A0A',
                        'hacker-gray': '#121212',
                        'hacker-light-gray': '#1E1E1E',
                        'hacker-green': '#00FF00',
                        'hacker-red': '#FF0000',
                        'hacker-blue': '#0088FF',
                    },
                    fontFamily: {
                        mono: ['JetBrains Mono', 'monospace'],
                    },
                    borderRadius: {
                        'hacker': '28px',
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
            .backdrop-blur-custom { backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); }
            .transition-all-smooth { transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
            .glow-green { text-shadow: 0 0 8px #00FF00; }
            .glow-border { box-shadow: 0 0 12px #00FF0020; }
        }
    </style>
</head>
<body class="bg-hacker-black text-green-400 font-mono min-h-screen flex flex-col overflow-x-hidden selection:bg-green-500 selection:text-black">
    <div class="fixed inset-0 z-0 bg-[radial-gradient(ellipse_at_center,_#001200_0%,_#000000_70%)]"></div>

    <main class="relative z-10 w-full min-h-screen flex items-center justify-center p-4">
        
        <!-- Login -->
        <section id="login-screen" class="w-full max-w-md transition-all-smooth opacity-100 scale-100">
            <div class="bg-hacker-dark/90 backdrop-blur-custom rounded-hacker border border-green-500/30 shadow-2xl p-6 md:p-8 glow-border">
                <div class="text-center mb-8">
                    <h1 class="text-[clamp(1.8rem,4vw,2.5rem)] font-black text-green-400 glow-green mb-2 tracking-wider">
                        &lt;/&gt; TASK_PRIME
                    </h1>
                    <p class="text-green-500/70 text-sm">// HACKER EDITION // GOD MODE</p>
                </div>

                <form id="login-form" class="space-y-5">
                    <div>
                        <label class="block text-sm font-bold text-green-300 mb-2">&gt; RA</label>
                        <input type="text" id="ra" class="w-full px-4 py-3 bg-hacker-gray border border-green-600/40 rounded-hacker focus:outline-none focus:border-green-400 text-green-300" placeholder="INPUT_RA">
                    </div>
                    <div>
                        <label class="block text-sm font-bold text-green-300 mb-2">&gt; SENHA</label>
                        <input type="password" id="senha" class="w-full px-4 py-3 bg-hacker-gray border border-green-600/40 rounded-hacker focus:outline-none focus:border-green-400 text-green-300" placeholder="INPUT_PASS">
                    </div>
                    <div>
                        <label class="block text-sm font-bold text-green-300 mb-2">&gt; CF_TOKEN (OPCIONAL)</label>
                        <input type="text" id="cf" class="w-full px-4 py-3 bg-hacker-gray border border-green-600/40 rounded-hacker focus:outline-none focus:border-green-400 text-green-300" placeholder="BYPASS_CLOUDFLARE">
                    </div>

                    <button type="submit" class="w-full py-3 bg-green-500 hover:bg-green-400 text-black font-black rounded-hacker transition-all-smooth glow-border mt-2 uppercase">
                        &gt; EXECUTAR_LOGIN
                    </button>
                </form>
            </div>
        </section>

        <!-- Modal Principal -->
        <section id="main-modal" class="hidden w-full max-w-lg transition-all-smooth opacity-0 scale-95">
            <div class="bg-hacker-dark/90 backdrop-blur-custom rounded-hacker border border-green-500/30 shadow-2xl overflow-hidden glow-border">
                
                <!-- Cabeçalho -->
                <div class="flex items-center justify-between p-5 border-b border-green-600/30 bg-green-900/10">
                    <h2 class="text-lg font-black text-green-400 glow-green tracking-wider">&lt;/&gt; SELECIONAR_ALVO</h2>
                    <button id="btn-close" class="text-green-500 hover:text-green-300 text-2xl transition-all-smooth">
                        <i class="fa fa-times-circle"></i>
                    </button>
                </div>

                <!-- Lista -->
                <div class="p-5 max-h-[65vh] overflow-y-auto scrollbar-hide">
                    <label class="flex items-center gap-3 mb-6 text-green-300 font-bold cursor-pointer">
                        <input type="checkbox" id="select-all" class="w-5 h-5 accent-green-500 rounded-sm">
                        <span>&gt; SELECIONAR_TODOS</span>
                    </label>

                    <div id="tasks-list" class="space-y-3 mb-6">
                        <div class="text-center text-green-700/70 py-6 font-bold">// CLICK: BUSCAR_ATIVIDADES</div>
                    </div>

                    <p class="text-xs text-green-600/60 mb-6 italic">
                        * PONTUACAO: VALOR < 100 = MAIOR_CHANCE_ERRO
                    </p>

                    <!-- Tempo -->
                    <div class="grid grid-cols-2 gap-5 mb-2">
                        <div>
                            <label class="block text-sm font-bold text-green-400 mb-2">&gt; TEMPO_MIN (MIN)</label>
                            <input type="number" id="min-time" value="1" min="1" class="w-full px-3 py-2.5 bg-hacker-gray border border-green-600/40 rounded-hacker text-center text-green-300 font-bold">
                        </div>
                        <div>
                            <label class="block text-sm font-bold text-green-400 mb-2">&gt; TEMPO_MAX (MIN)</label>
                            <input type="number" id="max-time" value="3" min="1" class="w-full px-3 py-2.5 bg-hacker-gray border border-green-600/40 rounded-hacker text-center text-green-300 font-bold">
                        </div>
                    </div>
                </div>

                <!-- Botões -->
                <div class="p-5 border-t border-green-600/30 bg-green-900/10 space-y-3">
                    <button id="btn-run" class="w-full py-3 bg-green-500 hover:bg-green-400 text-black font-black rounded-hacker transition-all-smooth glow-border uppercase">
                        &gt; EXECUTAR_SELECIONADAS
                    </button>
                    <button id="btn-draft" class="w-full py-2.5 bg-hacker-gray border border-green-800/50 text-green-700/50 rounded-hacker cursor-not-allowed uppercase">
                        // RASCUNHO
                    </button>
                    <button id="btn-refresh" class="w-full py-2.5 bg-hacker-light-gray hover:bg-hacker-gray text-green-400 rounded-hacker transition-all-smooth text-sm font-bold border border-green-700/30 uppercase">
                        <i class="fa fa-refresh mr-2"></i> BUSCAR_ATIVIDADES
                    </button>
                </div>
            </div>
        </section>

    </main>

    <!-- Notificações -->
    <div id="notifications" class="fixed top-5 right-5 z-50 space-y-3 w-full max-w-xs"></div>

    <script>
        let state = { token: null, captcha: null, cf: null, tasks: [], running: false };

        function notify(msg, type='info'){
            const cont = document.getElementById('notifications');
            const colors = {
                success: 'bg-green-900/80 border-green-400 text-green-300',
                error: 'bg-red-900/80 border-red-400 text-red-300',
                info: 'bg-blue-900/80 border-blue-400 text-blue-300'
            };
            const el = document.createElement('div');
            el.className = `p-4 rounded-hacker border backdrop-blur-custom transition-all-smooth translate-x-0 opacity-0 font-bold ${colors[type]}`;
            el.innerHTML = `<div class="flex items-start gap-3"><i class="fa ${type==='success'?'fa-check-circle':'fa-exclamation-triangle'}"></i><span>${msg}</span></div>`;
            cont.appendChild(el);
            setTimeout(()=>el.classList.replace('opacity-0','opacity-100'),10);
            setTimeout(()=>{el.classList.add('opacity-0','translate-x-4');setTimeout(()=>el.remove(),300)},4000);
        }

        // Login
        document.getElementById('login-form').addEventListener('submit', async e=>{
            e.preventDefault();
            const btn = e.target.querySelector('button');
            btn.disabled=true; btn.innerHTML='<i class="fa fa-spinner fa-spin mr-2"></i> PROCESSANDO...';
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

                notify(`ACESSO_PERMITIDO: ${d.nome.toUpperCase()}`,'success');
                
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
                btn.disabled=false; btn.innerHTML='&gt; EXECUTAR_LOGIN';
            }
        });

        // ✅ BUSCA CORRIGIDA = MESMA LÓGICA DO SEU CÓDIGO QUE FUNCIONAVA
        document.getElementById('btn-refresh').addEventListener('click', async ()=>{
            try{
                notify('SOLICITANDO_DADOS...','info');
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
                    notify('NENHUMA_ATIVIDADE_ENCONTRADA','info');
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
            if(!list.length){el.innerHTML='<div class="text-center text-red-500/70 py-6 font-bold">// VAZIO //</div>';return;}
            
            list.forEach((t, i)=>{
                const div=document.createElement('div');
                div.className='flex items-center justify-between gap-2 p-3 hover:bg-green-900/20 rounded-hacker transition-all-smooth border border-green-800/40';
                div.dataset.id=t.id;
                div.dataset.target=t.publication_target;
                div.innerHTML=`
                    <label class="flex items-center gap-3 flex-1 cursor-pointer">
                        <input type="checkbox" class="task-checkbox w-4 h-4 accent-green-500 rounded-sm">
                        <span class="text-sm text-green-300 line-clamp-1">&gt; TASK_${i+1}: ${t.title}</span>
                    </label>
                    <select class="score-select bg-hacker-gray border border-green-600/40 rounded-hacker px-2 py-1 text-xs text-green-400 font-bold">
                        <option value="100">100%</option>
                        <option value="90">90%</option>
                        <option value="80">80%</option>
                        <option value="70">70%</option>
                        <option value="50">50%</option>
                    </select>
                `;
                el.appendChild(div);
            });

            document.getElementById('select-all').onchange=e=>{
                document.querySelectorAll('.task-checkbox').forEach(cb=>cb.checked=e.target.checked);
            };
        }

        // Executar ✅ SEM ERRO
        document.getElementById('btn-run').addEventListener('click', async ()=>{
            if(state.running) return notify('PROCESSO_ATIVO','info');
            
            const selecionadas=[];
            document.querySelectorAll('#tasks-list > div').forEach(div=>{
                const cb=div.querySelector('.task-checkbox');
                if(cb.checked){
                    selecionadas.push({
                        id:div.dataset.id,
                        target:div.dataset.target,
                        score:parseInt(div.querySelector('.score-select').value)
                    });
                }
            });

            if(!selecionadas.length) return notify('NENHUMA_TASK_SELECIONADA','error');

            const minT=parseInt(document.getElementById('min-time').value);
            const maxT=parseInt(document.getElementById('max-time').value);

            if(minT>maxT) return notify('TEMPO_INVALIDO','error');

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
                            cf:state.cf,
                            score:atv.score
                        })
                    });
                    const d=await res.json();
                    if(!res.ok) throw new Error(d.detail);

                    notify(`✅ SUCESSO [${i+1}]`,'success');
                    await new Promise(r=>setTimeout(r,800));

                }catch(err){
                    notify(`❌ FALHA [${i+1}]: ${err.message}`,'error');
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
