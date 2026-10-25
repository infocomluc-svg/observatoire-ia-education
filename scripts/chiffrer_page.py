#!/usr/bin/env python3
"""
Verrouille une page de l'Info lettre IANE par mot de passe.

Usage : python3 scripts/chiffrer_page.py PAGE_EN_CLAIR.html PAGE_PUBLIEE.html

- Le contenu de la page est chiffré (AES-256-GCM) avec une clé aléatoire,
  elle-même chiffrée avec la clé publique de infolettre-iane/cle.json (RSA-OAEP).
- Ce script n'a besoin d'AUCUN mot de passe : seule la clé publique sert à chiffrer.
- Le navigateur déchiffre la page quand le visiteur saisit le bon mot de passe.
- Ne jamais enregistrer la page en clair dans le dépôt.
Dépendance : pip install cryptography
"""
import base64, html, json, os, pathlib, re, sys

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

RACINE = pathlib.Path(__file__).resolve().parent.parent
CLE = json.loads((RACINE / "infolettre-iane" / "cle.json").read_text(encoding="utf-8"))

COQUILLE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<title>__TITRE__</title>
<style>
:root{--bg:#f3f5fb;--paper:#fff;--ink:#141b34;--muted:#46506e;--line:#dde2f0;--accent:#3046c8;--err:#c0392b;--hero:#1b2a8f}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0c1022;--paper:#151a33;--ink:#eef1ff;--muted:#b3bad8;--line:#283058;--accent:#8c9bff;--err:#ff7b7f;--hero:#151f6e;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;
  padding:24px max(16px,env(safe-area-inset-right,0px)) 24px max(16px,env(safe-area-inset-left,0px))}
.box{width:100%;max-width:420px;background:var(--paper);border:1px solid var(--line);border-radius:16px;padding:28px;box-shadow:0 12px 32px -18px rgba(0,0,0,.35)}
.lock{width:52px;height:52px;border-radius:14px;background:var(--hero);color:#fff;display:grid;place-items:center;font-size:24px;margin-bottom:14px}
h1{font-size:22px;margin:0 0 6px;line-height:1.25}
p{color:var(--muted);margin:0 0 18px}
label{display:block;font-weight:600;font-size:14px;margin-bottom:6px}
.row{display:flex;gap:8px}
input{flex:1;min-width:0;font:inherit;padding:11px 12px;border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--ink)}
input:focus,button:focus-visible,a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
button{font:inherit;font-weight:700;border:0;border-radius:10px;padding:11px 16px;background:var(--accent);color:#fff;cursor:pointer}
button[disabled]{opacity:.6;cursor:wait}
.msg{min-height:1.4em;margin:10px 0 0;font-size:14px;color:var(--err)}
.back{display:inline-block;margin-top:18px;font-size:14px;color:var(--accent)}
noscript{display:block;margin-top:12px;color:var(--err)}
</style>
</head>
<body>
<main class="box">
  <div class="lock" aria-hidden="true">🔒</div>
  <h1>Espace réservé</h1>
  <p>__TITRE__. Saisissez le mot de passe communiqué par Luc Masson.</p>
  <form id="f" autocomplete="off">
    <label for="pw">Mot de passe</label>
    <div class="row"><input id="pw" type="password" required autofocus><button id="go" type="submit">Entrer</button></div>
    <p class="msg" id="msg" role="alert"></p>
  </form>
  <a class="back" href="__RETOUR__">← Retour à l'Observatoire IA Éducation</a>
  <noscript>Cette page nécessite JavaScript.</noscript>
</main>
<script id="payload" type="application/json">__DONNEES__</script>
<script>
(function(){
  var KEY='iane-cle-privee';
  var D=JSON.parse(document.getElementById('payload').textContent);
  var S=window.crypto&&window.crypto.subtle;
  function b(s){var r=atob(s),a=new Uint8Array(r.length);for(var i=0;i<r.length;i++)a[i]=r.charCodeAt(i);return a}
  function b64(buf){var a=new Uint8Array(buf),s='';for(var i=0;i<a.length;i++)s+=String.fromCharCode(a[i]);return btoa(s)}
  function ouvrir(pk8){
    return S.importKey('pkcs8',pk8,{name:'RSA-OAEP',hash:'SHA-256'},false,['decrypt'])
      .then(function(k){return S.decrypt({name:'RSA-OAEP'},k,b(D.ek))})
      .then(function(raw){return S.importKey('raw',raw,'AES-GCM',false,['decrypt'])})
      .then(function(k){return S.decrypt({name:'AES-GCM',iv:b(D.iv)},k,b(D.ct))})
      .then(function(buf){var h=new TextDecoder().decode(buf);document.open();document.write(h);document.close()});
  }
  function deverrouiller(pw){
    return fetch('cle.json',{cache:'no-store'}).then(function(r){if(!r.ok)throw new Error('cle');return r.json()}).then(function(C){
      return S.importKey('raw',new TextEncoder().encode(pw),'PBKDF2',false,['deriveKey'])
        .then(function(m){return S.deriveKey({name:'PBKDF2',salt:b(C.salt),iterations:C.iterations,hash:'SHA-256'},m,{name:'AES-GCM',length:256},false,['decrypt'])})
        .then(function(k){return S.decrypt({name:'AES-GCM',iv:b(C.iv)},k,b(C.cle_privee_chiffree))});
    });
  }
  if(!S){document.getElementById('msg').textContent='Votre navigateur ne permet pas d\\'ouvrir cette page (connexion sécurisée https requise).';return}
  var memo=null;try{memo=sessionStorage.getItem(KEY)}catch(e){}
  if(memo){ouvrir(b(memo)).catch(function(){try{sessionStorage.removeItem(KEY)}catch(e){}})}
  document.getElementById('f').addEventListener('submit',function(e){
    e.preventDefault();
    var btn=document.getElementById('go'),msg=document.getElementById('msg');
    btn.disabled=true;msg.textContent='';
    deverrouiller(document.getElementById('pw').value).then(function(pk8){
      try{sessionStorage.setItem(KEY,b64(pk8))}catch(e){}
      return ouvrir(pk8);
    }).catch(function(err){
      btn.disabled=false;
      msg.textContent=(err&&err.message==='cle')?'Fichier de clé introuvable. Réessayez plus tard.':'Mot de passe incorrect.';
      document.getElementById('pw').select();
    });
  });
})();
</script>
</body>
</html>
"""


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage : python3 scripts/chiffrer_page.py PAGE_EN_CLAIR.html PAGE_PUBLIEE.html")
    clair = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
    m = re.search(r"<title>(.*?)</title>", clair, re.S)
    titre = html.unescape(m.group(1).strip()) if m else "Info lettre IANE"
    cle_aes = AESGCM.generate_key(bit_length=256)
    iv = os.urandom(12)
    ct = AESGCM(cle_aes).encrypt(iv, clair.encode("utf-8"), None)
    pub = serialization.load_der_public_key(base64.b64decode(CLE["cle_publique"]))
    ek = pub.encrypt(cle_aes, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    b = lambda x: base64.b64encode(x).decode()
    donnees = json.dumps({"ek": b(ek), "iv": b(iv), "ct": b(ct)})
    page = (COQUILLE.replace("__TITRE__", html.escape(titre))
            .replace("__RETOUR__", "https://infocomluc-svg.github.io/observatoire-ia-education/")
            .replace("__DONNEES__", donnees))
    pathlib.Path(sys.argv[2]).write_text(page, encoding="utf-8")
    print(f"Page verrouillée : {sys.argv[2]} ({len(clair)} caractères chiffrés)")


if __name__ == "__main__":
    main()
