import urllib.request, json
KEY='6e07b8b7a4b04339b4dc85416e0d1605.9aExNzed07Fe81a8'
BASE='https://open.bigmodel.cn/api/paas/v4'
for m in ['glm-4.7-flash','glm-4.5-flash','glm-4-flash','glm-4.7','glm-4.6']:
    body=json.dumps({'model':m,'messages':[{'role':'user','content':'hi'}],'max_tokens':1}).encode()
    req=urllib.request.Request(BASE+'/chat/completions',data=body,
        headers={'Content-Type':'application/json','Authorization':'Bearer '+KEY},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            print('[200 OK]',m)
    except urllib.error.HTTPError as e:
        print('[%s]'%e.code,m,e.read().decode('utf-8','replace')[:140])
    except Exception as e:
        print('[ERR]',m,type(e).__name__,str(e)[:140])
