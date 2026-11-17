
// Rapport de contrôle (lu par controle.py via Chrome sans écran, page ouverte avec ?qa=1).
// Pour chaque texte : type, fenêtre d'images [f0, f1), boîte [x0, y0, x1, y1] dans l'image 1080x1920, s'il est sur la vidéo.
window.__qaRapport=function(){
  if(!/qa/.test(location.search))return;
  const root=document.getElementById('root'),R0=root.getBoundingClientRect(),k=R0.width/1080,NF=window.CFG.NF;
  const boite=els=>{let x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;for(const e of els){const r=e.getBoundingClientRect();if(!r.width&&!r.height)continue;
    x0=Math.min(x0,r.left);y0=Math.min(y0,r.top);x1=Math.max(x1,r.right);y1=Math.max(y1,r.bottom);}
    return x0>1e8?null:[(x0-R0.left)/k,(y0-R0.top)/k,(x1-R0.left)/k,(y1-R0.top)/k].map(v=>Math.round(v));};
  const out={style:root.dataset.style,polices:{ZTN:document.fonts.check('600 50px "ZTN"'),ITight:document.fonts.check('500 50px "ITight"'),ISerif:document.fonts.check('400 50px "ISerif"')},elements:[],blocs:[]};
  // fplein : image où le texte est entièrement construit (dernier mot entré + 6 images), pour la planche
  const plein=(el,f0,f1)=>{const fs=[...el.querySelectorAll('[data-f]')].map(x=>+x.dataset.f).filter(x=>x>=+f0&&x<+f1);return Math.max(+f0+2,Math.min(+f1-6,(fs.length?Math.max(...fs):+f0)+6));};
  const add=(type,id,f0,f1,box,surVideo,blanc,el)=>{if(box)out.elements.push({type,id,f0:+f0,f1:Math.min(+f1,NF),fplein:el?plein(el,f0,Math.min(+f1,NF)):+f0+6,box,surVideo,blanc});};
  if(root.dataset.style==='classique'){
    document.querySelectorAll('.cap').forEach((c,i)=>add('sous-titre','cap'+i,c.dataset.f0,c.dataset.f1,boite(c.querySelectorAll('.w')),true,true,c));
    document.querySelectorAll('.bloc').forEach(b=>add('bloc',b.id,b.dataset.f0,b.dataset.f1,boite(b.querySelectorAll('.w')),true,true,b));
    document.querySelectorAll('.depth').forEach(d=>add('profondeur',d.id,d.dataset.f0,d.dataset.f1,boite(d.querySelector('.roll')?[d.querySelector('.roll')]:d.querySelectorAll('.dw')),true,false,d));
    document.querySelectorAll('.card').forEach(c=>{const qs=[...c.querySelectorAll('.q')];
      qs.forEach((q,i)=>add('carton',c.id+'-q'+i,q.dataset.f0,c.classList.contains('stack')?c.dataset.f1:q.dataset.f1,boite(q.querySelectorAll('.w')),false,true,c));});
    document.querySelectorAll('.panel').forEach(p=>add('panneau','panneau',p.dataset.f0,p.dataset.f1,boite([p]),true,false,p));
    document.querySelectorAll('.wheel').forEach(w=>{const pas=JSON.parse(w.dataset.pas),kf=pas[pas.length-1][1],its=[...w.querySelectorAll('.it')],top=w.getBoundingClientRect().top;
      const wr=w.getBoundingClientRect(),larg=Math.max(...its.map(i=>i.offsetWidth))+104,tg=w.querySelector('.wtag');
      const y0=(top-R0.top)/k-56-112,y1=(top-R0.top)/k+56+112,x0=(wr.left-R0.left)/k,x1=x0+larg+(tg?tg.offsetWidth+30:0);
      add('liste',w.id,w.dataset.f0,w.dataset.f1,[x0,y0,x1,y1].map(Math.round),true,true,w);});
  } else {
    document.querySelectorAll('.blk').forEach((b,i)=>{if(!b.__qa)return;const carte=!!b.closest('.card');
      out.blocs.push({id:'blk'+i,f0:+b.dataset.f0,f1:+b.dataset.f1,carton:carte,...b.__qa});
      b.__qa.pieces.forEach((p,j)=>add(p.classe==='s'?'sous-titre':'piece','blk'+i+'-'+j+' '+p.texte,Math.max(p.f0,+b.dataset.f0),Math.min(p.f1,+b.dataset.f1),p.box.map(Math.round),!carte,!/bleu|orange|violet/.test(p.couleur),b));});
  }
  const pre=document.createElement('pre');pre.id='qa-rapport';pre.textContent=JSON.stringify(out);document.body.appendChild(pre);
};
