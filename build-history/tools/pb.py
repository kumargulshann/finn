import re
def varint(b,i):
    r=s=0
    while True:
        x=b[i]; i+=1; r|=(x&0x7f)<<s; s+=7
        if x<0x80: return r,i
def parse(b):
    out=[]; i=0
    try:
        while i<len(b):
            k,i=varint(b,i); f,w=k>>3,k&7
            if f==0: return None
            if w==0: v,i=varint(b,i); out.append((f,'v',v))
            elif w==1: out.append((f,'64',b[i:i+8])); i+=8
            elif w==5: out.append((f,'32',b[i:i+4])); i+=4
            elif w==2:
                n,i=varint(b,i); 
                if i+n>len(b): return None
                out.append((f,'b',b[i:i+n])); i+=n
            else: return None
    except IndexError: return None
    return out
def is_text(s):
    try: t=s.decode('utf-8')
    except UnicodeDecodeError: return None
    if not t: return None
    bad=sum(1 for ch in t if ord(ch)<32 and ch not in '\n\r\t')
    return t if bad==0 else None
def strings(b,path=()):
    """yield (path, text) for leaf strings; prefer submessage parse when string isn't clearly text"""
    for f,w,v in parse(b) or []:
        if w!='b': continue
        p=path+(f,)
        t=is_text(v)
        sub=parse(v) if v else None
        # treat as text if decodable and looks like natural text; else recurse
        if t is not None and (sub is None or re.search(r'[a-zA-Z]{3,} [a-zA-Z]{2,}|[{}:"/]',t) and len(t)>30 or sub is None):
            yield p,t
        elif sub is not None:
            yield from strings(v,p)
        elif t is not None:
            yield p,t
