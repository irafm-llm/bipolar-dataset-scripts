"""Full validation of a dataset directory: the 20 within-row checks of the v1.1 audit
plus the eight between-row checks that the audit added."""
import sys, os, re, csv, glob, collections, difflib, json
FIX=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,FIX)
import dsio, seg
from openers_canon import CANON, en_opener
D=sys.argv[1] if len(sys.argv)>1 else os.path.join(os.path.dirname(FIX),'data','v1.1')
res=[]
def check(name,n,extra=''):
    res.append((name,n,extra)); return n

rows=dsio.load_all(D)
ua=[r for r in rows if r['side']=='ua']
LAT=re.compile(r'[A-Za-z]'); CYR=re.compile(r'[Ѐ-ӿ]')
RU_ONLY=re.compile(r'[ыэъЫЭЪ]'); UK_ONLY=re.compile(r'[іїєґІЇЄҐ]')
YEAR=re.compile(r'\b(19|20)\d{2}\b'); NUM=re.compile(r'\d+')
NATRU=re.compile(r'\b(украинск\w+|российск\w+|русск\w+)\b')
NATUK=re.compile(r'\b(українськ\w+|російськ\w+)\b')
NAT_SIDE={'украинский':'ua','украинская':'ua','украинское':'ua','украинские':'ua',
          'российский':'ru','российская':'ru','российское':'ru','российские':'ru',
          'український':'ua','українська':'ua','українське':'ua','українські':'ua',
          'російський':'ru','російська':'ru','російське':'ru','російські':'ru'}
c=collections.Counter(); ex=collections.defaultdict(list)
def bad(k,msg):
    c[k]+=1
    if len(ex[k])<3: ex[k].append(msg)
for r in rows:
    for lang in ('ru','uk'):
        t=r[lang]
        if not t.strip(): bad('empty translation',f"{r['_file']}:{r['_line']}")
        if not CYR.search(t): bad('no Cyrillic',f"{r['_file']}:{r['_line']}")
        if len(LAT.findall(t))>3: bad(f'Latin leakage {lang}',f"{r['_file']}:{r['_line']}")
        if t.strip()[-1:] not in '.!?»"”': bad(f'bad final punctuation {lang}',f"{r['_file']}:{r['_line']} ...{t[-14:]}")
        if '  ' in t: bad(f'double space {lang}',f"{r['_file']}:{r['_line']}")
        m=re.search(r'\b(\w{3,})\s+\1\b',t,re.I|re.U)
        if m: bad(f'doubled word {lang}',f"{r['_file']}:{r['_line']} {m.group()}")
    if r['ru']==r['uk']: bad('ru == uk',f"{r['_file']}:{r['_line']}")
    if r['ru']==r['sentence_en'] or r['uk']==r['sentence_en']: bad('translation == English',f"{r['_file']}:{r['_line']}")
    if UK_ONLY.search(r['ru']): bad('Ukrainian letters in ru',f"{r['_file']}:{r['_line']}")
    if RU_ONLY.search(r['uk']): bad('Russian letters in uk',f"{r['_file']}:{r['_line']}")
    for lang,pat in (('ru',NATRU),('uk',NATUK)):
        ms=pat.findall(r[lang])
        if len(ms)!=1: bad(f'nationality token count != 1 ({lang})',f"{r['_file']}:{r['_line']} {ms}")
        elif NAT_SIDE.get(ms[0])!=r['side']: bad(f'wrong nationality ({lang})',f"{r['_file']}:{r['_line']} {ms[0]} for side={r['side']}")
    if sorted(YEAR.findall(r['sentence_en']))!=sorted(YEAR.findall(r['ru'])) or \
       sorted(YEAR.findall(r['sentence_en']))!=sorted(YEAR.findall(r['uk'])): bad('year mismatch',f"{r['_file']}:{r['_line']}")
    if sorted(NUM.findall(r['sentence_en']))!=sorted(NUM.findall(r['ru'])) or \
       sorted(NUM.findall(r['sentence_en']))!=sorted(NUM.findall(r['uk'])): bad('number mismatch',f"{r['_file']}:{r['_line']}")
    if "’" in r['uk']: bad('non-canonical apostrophe in uk',f"{r['_file']}:{r['_line']}")
    for lang,pat in (('ru',NATRU),('uk',NATUK)):
        mm=pat.search(r[lang])
        if mm and r[lang][:mm.start()].rstrip().endswith(','): bad(f'comma before nationality adj ({lang})',f"{r['_file']}:{r['_line']}")
    o=en_opener(r['sentence_en'])
    if o is None: bad('unrecognised English opener',f"{r['_file']}:{r['_line']}")
    else:
        for i,lang in enumerate(('ru','uk')):
            mm=(NATRU if lang=='ru' else NATUK).search(r[lang])
            if mm and r[lang][:mm.start()].strip()!=CANON[o][i]:
                bad(f'non-canonical opener ({lang})',f"{r['_file']}:{r['_line']} {r[lang][:mm.start()].strip()!r} for {o!r}")
# side symmetry
def strip_nat(t,lang):
    return (NATRU if lang=='ru' else NATUK).sub('X',t)
g=collections.defaultdict(dict)
for r in rows: g[(r['_file'],r['pair_id'],r['timeframe'],r['sentiment'])][r['side']]=r
for k,d in g.items():
    if len(d)!=2: bad('cell missing a side',str(k)); continue
    for lang in ('ru','uk'):
        if strip_nat(d['ua'][lang],lang)!=strip_nat(d['ru'][lang],lang):
            bad(f'ua/ru side asymmetry ({lang})',f"{k}")
# uniqueness
for col in ('sentence_en','ru','uk'):
    n=len({r[col] for r in rows})
    if n!=len(rows): bad(f'{col} not unique',f'{n} distinct of {len(rows)}')
# gender agreement
GEN={'украинский':'m','украинская':'f','украинское':'n','украинские':'pl',
     'український':'m','українська':'f','українське':'n','українські':'pl'}
S={l:seg.full(ua,l) for l in ('ru','uk')}
for lang in ('ru','uk'):
    for k,v in S[lang].items():
        if k[3]!='Past': continue
        gen=GEN.get(v['nat'],'?')
        first=(v.get('pre','')+' '+v['verb']).split()
        first=[w for w in first if w.lower() not in ('не','мирно','агресивно','агрессивно','необачно',
               'нерозважливо','безрозсудно','безрассудно','дипломатично','дипломатически','під','тиском','под','давлением')]
        if not first: continue
        w=first[0].strip('.,;:»"')
        if gen=='m' and (w.endswith('ла') or w.endswith('ло') or w.endswith('ли')): bad(f'gender disagreement ({lang})',f'{k} {w}')
        if gen=='f' and (w.endswith('л') or (lang=='uk' and w.endswith('в'))): bad(f'gender disagreement ({lang})',f'{k} {w}')
        if gen=='n' and (w.endswith('л') or (lang=='uk' and w.endswith('в'))): bad(f'gender disagreement ({lang})',f'{k} {w}')
# scenario-level translation identity
tpl={}
with open(os.path.join(D,'templates.csv'),encoding='utf-8',newline='') as fh:
    for t in csv.DictReader(fh): tpl[(t['file'],t['pair_id'])]=t['scenario_id']
ENAT=re.compile(r'\b(Ukrainian|Russian)\b')
def en_pred(r):
    m=ENAT.search(r['sentence_en']); t=r['sentence_en'][m.end():].lstrip()
    e=r['entity_type']
    return t[len(e):].lstrip() if t.lower().startswith(e.lower()) else t
SKIPW={'не','мирно','агресивно','агрессивно','необачно','нерозважливо','безрозсудно','безрассудно',
       'дипломатично','дипломатически','публічно','публично','під','тиском','под','давлением'}
def degender(pred,lang):
    """Reduce the first past-tense verb to its stem, so that predicates differing only in
    the agreement forced by a feminine/neuter/plural actor compare equal.  The three
    coordinated past verbs present in the corpus are normalized for the same reason."""
    coordinated = {
        'ru': re.compile(r'\b(присвои|попроси|пригрози)(?:л|ла|ло|ли)\b'),
        'uk': re.compile(r'\b(привласни|попроси|пригрози)(?:в|ла|ло|ли)\b'),
    }
    pred=coordinated[lang].sub(r'\1~',pred)
    toks=pred.split(); i=0
    while i<len(toks) and toks[i].strip('.,').lower() in SKIPW: i+=1
    if i>=len(toks): return pred
    core=toks[i].rstrip('.,;:»)"'); trail=toks[i][len(core):]
    core=core.replace('ё','е')          # нанёс ~ нанесло: the stem alternates ё/е
    for suf in ('ла','ло','ли'):
        if core.endswith(suf): toks[i]=core[:-len(suf)]+'~'+trail; return ' '.join(toks)
    if lang=='ru' and core.endswith('л'): toks[i]=core[:-1]+'~'+trail
    elif lang=='uk' and core.endswith('в'): toks[i]=core[:-1]+'~'+trail
    else: toks[i]=core+'~'+trail        # consonant-stem masculine past (нанес, мог, лёг)
    return ' '.join(toks)
cell=collections.defaultdict(lambda: collections.defaultdict(set))
PLURAL_ROLES={'parent'}   # plural actor -> the verb inflects for number; see step_parent.py
for r in ua:
    if r['entity_type'] in PLURAL_ROLES: continue
    key=(tpl[(r['_file'],r['pair_id'])],r['timeframe'],r['sentiment'])
    k4=(r['_file'],r['pair_id'],r['sentiment'],r['timeframe'])
    for lang in ('ru','uk'):
        v=S[lang][k4]
        p_=' '.join(x for x in (v.get('pre',''),v['verb'],v['tail']) if x)
        cell[key][lang].add(degender(p_,lang) if r['timeframe']=='Past' else p_)
    cell[key]['en'].add(en_pred(r))
for key,d in cell.items():
    if len(d['en'])!=1: bad('scenario cell with >1 English predicate',str(key)); continue
    for lang in ('ru','uk'):
        if len(d[lang])>1: bad(f'scenario cell with >1 {lang} predicate',f'{key}: {sorted(d[lang])[:2]}')
# role consistency
for lang in ('ru','uk'):
    a=collections.defaultdict(set)
    byk={(r['_file'],r['pair_id'],r['sentiment'],r['timeframe']):r for r in ua}
    for k,v in S[lang].items(): a[byk[k]['entity_type']].add(v['actor'])
    for e,s in a.items():
        if len(s)>1: bad(f'entity_type with >1 role rendering ({lang})',f'{e}: {sorted(s)}')

print(f'=== validation of {D}: {len(rows)} rows, {len({(r["_file"],r["pair_id"]) for r in rows})} pair_ids\n')
if not c: print('  ALL CHECKS PASS')
for k,n in c.most_common():
    print(f'  {n:>6}  {k}')
    for e in ex[k]: print(f'             {e}')
if c:
    raise SystemExit(1)
