"""Publish an authorized source snapshot. Credential is read only from stdin.

No authentication material is written to a file, remote URL or Git config.
The ephemeral askpass program reads its password from the child environment.
"""
import argparse,base64,json,os,subprocess,sys,tempfile,urllib.request,urllib.error
from pathlib import Path


def main():
    a=argparse.ArgumentParser();a.add_argument('--snapshot',type=Path,required=True);a.add_argument('--owner',required=True)
    a.add_argument('--repo',default='cartoon-face-generator');a.add_argument('--report',type=Path,required=True);args=a.parse_args()
    print('Awaiting GitHub credential on private stdin (not saved).',flush=True)
    token=sys.stdin.readline().strip()
    if not token:raise ValueError('Missing credential')
    permissions={}
    def api(method,path,data=None):
        req=urllib.request.Request('https://api.github.com'+path,method=method,
          data=None if data is None else json.dumps(data).encode(),
          headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=60) as response:
            scopes=response.headers.get('X-OAuth-Scopes')
            if scopes is not None:permissions['scopes']=[s.strip() for s in scopes.split(',') if s.strip()]
            return json.load(response)
    login=api('GET','/user')['login']
    if login.casefold()!=args.owner.casefold():raise ValueError('Authenticated account does not match requested owner')
    print('Authenticated requested account: '+login,flush=True)
    selected=None
    for name in (args.repo,args.repo+'-101'):
        try:repo=api('GET',f'/repos/{args.owner}/{name}')
        except urllib.error.HTTPError as error:
            if error.code!=404:raise
            repo=api('POST','/user/repos',{'name':name,'private':False,'description':'Parametric SVG cartoon face: 101 semantic landmarks, 100 expression recipes, synthetic datasets and CPU MediaPipe webcam mapping.','auto_init':False})
            selected=repo;break
        try:api('GET',f'/repos/{args.owner}/{name}/commits?per_page=1')
        except urllib.error.HTTPError as error:
            if error.code==409:selected=repo;break
            raise
    if selected is None:raise ValueError('Both proposed repository names already contain commits; no existing project was overwritten')
    snapshot=args.snapshot.resolve();url=selected['clone_url'];repo_name=selected['name']
    existing=(snapshot/'.git').exists()
    if existing:
        origin=subprocess.check_output(['git','remote','get-url','origin'],cwd=snapshot,text=True).strip()
        if origin!=url:raise ValueError('Snapshot origin does not match requested repository')
        if subprocess.check_output(['git','rev-list','--count','HEAD'],cwd=snapshot,text=True).strip()!='1':raise ValueError('Retry expects only the unpublished initial snapshot commit')
    else:subprocess.run(['git','init','-b','main'],cwd=snapshot,check=True,stdout=subprocess.DEVNULL)
    actions_enabled='workflow' in permissions.get('scopes',[])
    if not actions_enabled:
        ci=snapshot/'.github/workflows/ci.yml'
        if ci.exists():
            # Ordinary repo-write credentials may lack the separate workflow
            # scope. Preserve the optional configuration as an inert template.
            target=snapshot/'tools/github_ci_template.yml';target.write_bytes(ci.read_bytes());ci.unlink()
            print('Credential has no workflow scope; publishing CI as an optional inert template.',flush=True)
    subprocess.run(['git','add','--all'],cwd=snapshot,check=True)
    command=['git','-c','user.name=Cartoon Face contributors','-c','user.email=contributors@users.noreply.github.com','commit']
    command+=['--amend','--no-edit'] if existing else ['-m','Publish shared SVG rig, expression catalogs, dataset tools and CPU webcam demo']
    subprocess.run(command,cwd=snapshot,check=True,stdout=subprocess.DEVNULL)
    if not existing:subprocess.run(['git','remote','add','origin',url],cwd=snapshot,check=True)
    with tempfile.TemporaryDirectory(prefix='cartoon-git-auth-') as auth:
        ask=Path(auth)/'askpass.py';ask.write_text('#!/usr/bin/env python3\nimport os,sys\nprint("x-access-token" if "username" in sys.argv[1].lower() else os.environ["CARTOON_EPHEMERAL_GH_TOKEN"])\n');ask.chmod(0o700)
        env={k:v for k,v in os.environ.items() if not k.startswith('GIT_TRACE') and k!='GIT_CURL_VERBOSE'}
        env.update(GIT_ASKPASS=str(ask),GIT_TERMINAL_PROMPT='0',CARTOON_EPHEMERAL_GH_TOKEN=token)
        pushed=subprocess.run(['git','-c','credential.helper=','push','--quiet','--no-progress','-u','origin','main'],cwd=snapshot,env=env,text=True,capture_output=True)
        if pushed.returncode:
            print(pushed.stderr[-3000:],flush=True);raise RuntimeError('GitHub push rejected or failed; see the sanitized Git error above')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=snapshot,text=True).strip()
    try:
        release=api('POST',f'/repos/{args.owner}/{repo_name}/releases',{'tag_name':'v1.0.0','name':'SVG face rig and CPU webcam demo',
          'body':'Shared 101-landmark SVG face rig, 40 EmoNet and 60 authored social recipes, smooth under-eye morphing, synthetic dataset/augmentation tools, and a standalone CPU MediaPipe laptop demo. See README for measured validation and scope.','draft':False,'prerelease':False})
        asset_info=None;model_info=None
        for filename in ('cartoon_webcam_mapper.zip','cartoon_landmarks_best.pt'):
            asset=snapshot.parent/filename
            if not asset.exists():continue
            upload=release['upload_url'].split('{')[0]+'?name='+filename
            req=urllib.request.Request(upload,method='POST',data=asset.read_bytes(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/zip' if filename.endswith('.zip') else 'application/octet-stream','Accept':'application/vnd.github+json'})
            with urllib.request.urlopen(req,timeout=120) as response:info=json.load(response)
            if filename.endswith('.zip'):asset_info=info
            else:model_info=info
    except urllib.error.HTTPError as error:
        print(f'Source published; release asset upload returned HTTP {error.code}.',flush=True);release=None;asset_info=None;model_info=None
    result={'repository':selected['html_url'],'commit':commit,'snapshot':str(snapshot),'release':release['html_url'] if release else None,
      'webcam_download':asset_info['browser_download_url'] if asset_info else None,'landmark_model_download':model_info['browser_download_url'] if model_info else None,'public':not selected['private'],'credentials_saved':False,'github_actions_enabled':actions_enabled}
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)


if __name__=='__main__':main()
