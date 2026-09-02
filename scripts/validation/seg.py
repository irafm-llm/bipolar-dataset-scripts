"""Segment a translated sentence into OPENER | NAT | ACTOR | VERB | TAIL.

VERB is located empirically: within one (file, pair_id, sentiment) the three timeframe
rows differ only in the opener and the verb form, so diffing them after the nationality
adjective isolates the verb span exactly.
"""
import re, collections, difflib
NAT={'ru':re.compile(r'\b(?:украинск\w+|российск\w+|русск\w+)\b'),
     'uk':re.compile(r'\b(?:українськ\w+|російськ\w+)\b')}
def split_nat(text,lang):
    m=NAT[lang].search(text)
    if not m: return None
    return text[:m.start()], text[m.start():m.end()], text[m.end():]
def toks(s): return s.split()

def verb_span(triple,lang):
    """triple: {timeframe: row}. Returns {timeframe: (i,j)} token span of the verb
    inside the post-nationality remainder, or None if it cannot be isolated."""
    rem={}
    for tf,r in triple.items():
        sp=split_nat(r[lang],lang)
        if not sp: return None
        rem[tf]=toks(sp[2])
    tfs=list(rem)
    ref=tfs[0]
    lo=None; hi=None
    for o in tfs[1:]:
        ops=[op for op in difflib.SequenceMatcher(None,rem[ref],rem[o],autojunk=False).get_opcodes() if op[0]!='equal']
        if not ops: continue
        a=min(op[1] for op in ops); b=max(op[2] for op in ops)
        lo=a if lo is None else min(lo,a); hi=b if hi is None else max(hi,b)
    if lo is None: return None
    # widen symmetrically per timeframe using the reference span
    out={}
    for tf in tfs:
        ops=[op for op in difflib.SequenceMatcher(None,rem[ref],rem[tf],autojunk=False).get_opcodes() if op[0]!='equal']
        if not ops: out[tf]=(lo,hi)
        else:
            j1=min(op[3] for op in ops); j2=max(op[4] for op in ops)
            out[tf]=(min(lo,j1),max(hi,j2))
    return out,rem

def segment(rows,lang):
    """rows: all ua-side rows. Returns dict (file,pair_id,sentiment,timeframe) ->
    dict(opener,nat,actor,verb,tail) for the given language."""
    g=collections.defaultdict(dict)
    for r in rows:
        g[(r['_file'],r['pair_id'],r['sentiment'])][r['timeframe']]=r
    out={}
    for k,triple in g.items():
        if len(triple)!=3: continue
        vs=verb_span(triple,lang)
        if vs is None: continue
        spans,rem=vs
        for tf,r in triple.items():
            i,j=spans[tf]
            sp=split_nat(r[lang],lang)
            t=rem[tf]
            out[k+(tf,)]={'opener':sp[0],'nat':sp[1],
                          'actor':' '.join(t[:i]),'verb':' '.join(t[i:j]),'tail':' '.join(t[j:])}
    return out


def peel_by_pairid(segments):
    """Split the actor span into the role phrase and any pre-verb predicate material.

    Within one (file, pair_id) the actor role is constant across all six
    (timeframe x sentiment) cells, so the role phrase is the longest common token
    prefix of the six actor spans; whatever follows in a given cell (negation,
    manner adverbs) belongs to the predicate and is kept in 'pre'.
    """
    import collections
    groups=collections.defaultdict(list)
    for k in segments: groups[(k[0],k[1])].append(k)   # (file, pair_id)
    for _,keys in groups.items():
        seqs=[segments[k]['actor'].split() for k in keys]
        n=0
        while n<min(len(x) for x in seqs) and len({tuple(x[:n+1]) for x in seqs})==1:
            n+=1
        for k in keys:
            t=segments[k]['actor'].split()
            segments[k]['actor']=' '.join(t[:n]); segments[k]['pre']=' '.join(t[n:])
    return segments

# Closed-class negation and manner adverbs. None of these is ever a role noun, so
# peeling them off the role phrase is unambiguous. Needed in addition to
# peel_by_pairid because in some categories (e.g. Disapprove) the negation is
# present in all six cells of a pair_id and so survives the common-prefix step.
PREVERB_FIXED={'не','мирно','агресивно','агрессивно','необачно','безрозсудно','безрассудно',
               'нерозважливо','дипломатично','дипломатически','публічно','публично'}
def peel_fixed(segments):
    for v in segments.values():
        t=v['actor'].split(); pre=[]
        while t and t[-1] in PREVERB_FIXED:
            pre.insert(0,t.pop())
        if pre:
            v['actor']=' '.join(t)
            v['pre']=(' '.join(pre)+' '+v.get('pre','')).strip()
    return segments
def full(rows,lang):
    return peel_fixed(peel_by_pairid(segment(rows,lang)))
