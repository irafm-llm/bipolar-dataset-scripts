"""Byte-preserving CSV I/O for the MIRROR-EN-UA-RU dataset.
UTF-8 no BOM, CRLF, QUOTE_MINIMAL -- as written by Python's csv module."""
import csv, glob, os
COLS=['pair_id','category','entity_type','timeframe','side','sentiment','sentence_en','ru','uk']
def files(d):
    return sorted(f for f in glob.glob(os.path.join(d,'*-*.csv')) if os.path.basename(f)[0].isdigit())
def load(path):
    with open(path,encoding='utf-8',newline='') as fh:
        rd=csv.DictReader(fh)
        assert rd.fieldnames==COLS, (path, rd.fieldnames)
        return [dict(r) for r in rd]
def save(path,rows):
    with open(path,'w',encoding='utf-8',newline='') as fh:
        w=csv.DictWriter(fh,fieldnames=COLS,lineterminator='\r\n')
        w.writeheader(); w.writerows(rows)
def load_all(d):
    out=[]
    for f in files(d):
        for i,r in enumerate(load(f),start=2):
            r['_file']=os.path.basename(f); r['_line']=i; out.append(r)
    return out
