const C=window.CFG,FPS=C.FPS,NF=C.NF,D=NF/FPS,T=fr=>(fr-.5)/FPS;
function placeDepth(el){
  const chiffre=el.classList.contains('chiffre'),v3=el.classList.contains('v3');
  const s=v3?(chiffre?el.querySelector('.roll'):el.querySelector('.dw')):el.querySelector('span');
  const cv=document.createElement('canvas').getContext('2d');
  let fs=200;el.style.fontSize=fs+'px';
  const txt=chiffre?(el.dataset.chiffre||'3'):s.textContent;
  cv.font=`400 ${fs}px "ISerif"`;let m=cv.measureText(txt);
  if(chiffre){fs=fs*700/m.actualBoundingBoxAscent;}else{fs=fs*(v3?900:960)/s.getBoundingClientRect().width;}
  el.style.fontSize=fs+'px';cv.font=`400 ${fs}px "ISerif"`;m=cv.measureText(txt);
  const asc=m.fontBoundingBoxAscent,desc=m.fontBoundingBoxDescent,cap=m.actualBoundingBoxAscent;
  const half=(fs-(asc+desc))/2,SY=(v3&&!chiffre)?C.ETIRE:1;
  const capTop=chiffre?(+el.dataset.haut||300):(+el.dataset.sommet)-0.4*cap*SY;
  el.style.top=(capTop+cap*SY-half-asc)+'px';el.style.left=((+el.dataset.cx)-540)+'px';
  if(SY!==1){s.style.transformOrigin=`50% ${half+asc}px`;s.style.transform=`scaleY(${SY})`;}
  el.dataset.cap=cap;
}
const ROND=[[-0.786,-0.809],[-0.459,-1.005],[0.465,-0.989],[0.8,-0.917],[0.985,-0.563],[0.981,0.341],[0.902,0.757],[0.642,1.069],[-0.159,1.076],[-0.695,0.979],[-0.927,0.76],[-1.009,0.253],[-0.953,-0.721],[-0.755,-0.964],[-0.386,-1.091]];
const TRAIT=[[-0.02,7.3],[0.153,7.2],[0.327,5.7],[0.5,7.0],[0.673,5.5],[0.847,3.6],[1.02,5.0]];
function lisse(a){let t=`M${a[0][0].toFixed(1)} ${a[0][1].toFixed(1)}`;for(let i=1;i<a.length-1;i++){const m=[(a[i][0]+a[i+1][0])/2,(a[i][1]+a[i+1][1])/2];
  t+=` Q${a[i][0].toFixed(1)} ${a[i][1].toFixed(1)} ${m[0].toFixed(1)} ${m[1].toFixed(1)}`;}const z=a[a.length-1];return t+` L${z[0].toFixed(1)} ${z[1].toFixed(1)}`;}
function poseTrace(t){
  const ws=t.mots.map(i=>document.querySelector(`.w[data-i="${i}"]`)).filter(Boolean);if(!ws.length)return null;
  const box=ws[0].closest('.q,.bloc,.cap'),k=document.getElementById('root').getBoundingClientRect().width/1080,cr=box.getBoundingClientRect();
  let x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;for(const w of ws){const r=w.getBoundingClientRect();x0=Math.min(x0,r.left);y0=Math.min(y0,r.top);x1=Math.max(x1,r.right);y1=Math.max(y1,r.bottom);}
  x0=(x0-cr.left)/k;x1=(x1-cr.left)/k;y0=(y0-cr.top)/k;y1=(y1-cr.top)/k;const w=x1-x0,h=y1-y0,cx=(x0+x1)/2,cy=(y0+y1)/2;
  const pts=t.forme==='rond'?ROND.map(([x,y])=>[cx+x*(w/2+36),cy+y*(h/2-0.1*h)]):TRAIT.map(([x,y])=>[x0+x*w,y1-3+y]);
  const NS='http://www.w3.org/2000/svg',sv=document.createElementNS(NS,'svg'),pa=document.createElementNS(NS,'path');
  sv.setAttribute('class','trace');sv.setAttribute('width',box.offsetWidth);sv.setAttribute('height',box.offsetHeight);
  pa.setAttribute('d',lisse(pts));pa.setAttribute('pathLength','100');pa.style.stroke=t.couleur;pa.style.strokeWidth=t.forme==='rond'?'5.5px':'11px';
  if(t.forme==='trait')sv.style.filter='drop-shadow(0 0 10px rgba(47,107,255,.75))';
  sv.appendChild(pa);box.appendChild(sv);return pa;
}
Promise.all([document.fonts.load('600 100px "ZTN"').catch(()=>0),document.fonts.load('700 100px "ZTN"').catch(()=>0),document.fonts.load('400 100px "ISerif"'),document.fonts.load('italic 400 100px "ISerif"'),document.fonts.load('500 100px "ITight"'),
  document.fonts.load('700 100px "ITight"'),document.fonts.load('400 30px "JMono"')]).then(()=>document.fonts.ready).then(()=>{
  document.querySelectorAll('.depth').forEach(placeDepth);
  for(const l of document.querySelectorAll('.ql')){const w=l.scrollWidth,mx=896,f0=parseFloat(getComputedStyle(l).fontSize);if(w>mx){l.style.fontSize=(f0*mx/w)+'px';}}
  for(const c of document.querySelectorAll('.card')){const qs=[...c.querySelectorAll('.q')];let top;
    if(c.classList.contains('stack')){const hs=qs.map(q=>q.offsetHeight),tot=hs.reduce((a,b)=>a+b,0)+40*(qs.length-1);top=Math.round(860-tot/2);let y=top;qs.forEach((q,i)=>{q.style.top=y+'px';y+=hs[i]+40;});}
    else{const h=Math.max(...qs.map(q=>q.offsetHeight));top=Math.round(860-h/2);qs.forEach(q=>q.style.top=top+'px');}
    c.querySelector('.clabel').style.top=(top-86)+'px';c.querySelector('.cnum').style.top=(top-86)+'px';}
  const traces=(C.TRACES||[]).map(t=>[t,poseTrace(t)]).filter(x=>x[1]);
  const fx=document.querySelector('.bloc.fx');
  const tl=gsap.timeline({paused:true});
  // caméra : poussée lente par plan, coups de zoom secs qui se posent
  for(let i=0;i<C.COUPES.length-1;i++){const a=C.COUPES[i],b=C.COUPES[i+1];
    tl.fromTo('#cam',{scale:1},{scale:1.035,duration:(b-a)/FPS,ease:'none',immediateRender:i===0},a?T(a):0);}
  for(const [f,z0,z1] of C.PUNCHS){const nxt=C.COUPES.find(c=>c>f);
    tl.set('#punch',{scale:z0},T(f));tl.to('#punch',{scale:z1,duration:.7,ease:'expo.out'},T(f)+.001);tl.set('#punch',{scale:1},T(nxt));}
  // sous-titres : chaque mot entre à son temps, flou vers net
  for(const c of document.querySelectorAll('.cap,.bloc')){const f0=+c.dataset.f0,f1=+c.dataset.f1,stat=c.classList.contains('statique');
    if(f0>0)tl.set(c,{visibility:'visible'},T(f0));else c.style.visibility='visible';
    if(!stat)for(const w of c.querySelectorAll('.w')){const big=w.closest('.big');
      tl.fromTo(w,{opacity:0,filter:big?'blur(18px)':'blur(9px)',y:big?14:8,scale:big?1.06:1},
        {opacity:1,filter:'blur(0px)',y:0,scale:1,duration:big?.32:.2,ease:'power3.out',immediateRender:false},T(+w.dataset.f));}
    tl.to(c,{opacity:0,filter:'blur(8px)',duration:.12,ease:'power2.in'},T(f1)-.12);tl.set(c,{visibility:'hidden'},T(f1));}
  // mots en profondeur : entrée 80 % -> 105 % -> 100 % en 6 images, la personne détourée par-dessus
  for(const d of document.querySelectorAll('.depth.v3')){const f0=+d.dataset.f0,f1=+d.dataset.f1,col=d.querySelector('.col'),dws=d.querySelectorAll('.dw');
    tl.set('#fg',{opacity:1},T(f0)-.001);
    tl.fromTo(d,{opacity:0,scale:.85,filter:'blur(18px)'},{opacity:1,scale:1.05,filter:'blur(0px)',duration:5/FPS,ease:'power2.out',immediateRender:false},T(f0));
    tl.to(d,{scale:1,duration:3/FPS,ease:'power1.inOut'},T(f0)+5/FPS);
    if(col){tl.fromTo(col,{yPercent:0},{yPercent:-100*(col.children.length-1)/col.children.length,duration:10/FPS,ease:'power3.out',immediateRender:false},T(f0));
      tl.fromTo(col,{filter:'blur(10px)'},{filter:'blur(0px)',duration:10/FPS,ease:'power2.in',immediateRender:false},T(f0));}
    tl.to(d,{y:-14,duration:(f1-f0)/FPS,ease:'none'},T(f0));
    for(const b of JSON.parse(d.dataset.brille||'[]'))tl.fromTo(dws,{'--sh':100},{'--sh':0,duration:.42,ease:'power2.inOut',immediateRender:false},T(b));
    tl.to(d,{opacity:0,filter:'blur(16px)',scale:1.04,duration:6/FPS,ease:'power2.in'},T(f1));
    tl.set('#fg',{opacity:0},T(f1)+7/FPS);}
  for(const d of document.querySelectorAll('.depth:not(.v3)')){const f0=+d.dataset.f0,f1=+d.dataset.f1;
    tl.set('#fg',{opacity:1},T(f0)-.001);
    tl.fromTo(d,{opacity:0,scale:.8,filter:'blur(10px)'},{opacity:1,scale:1.05,filter:'blur(0px)',duration:4/FPS,ease:'power2.out',immediateRender:false},T(f0));
    tl.to(d,{scale:1,duration:2/FPS,ease:'power1.inOut'},T(f0)+4/FPS);
    tl.to(d,{y:-14,duration:(f1-f0)/FPS,ease:'none'},T(f0));
    tl.to(d,{opacity:0,filter:'blur(12px)',duration:7/FPS,ease:'power2.in'},T(f1));
    tl.set('#fg',{opacity:0},T(f1)+8/FPS);}
  // cartons bleus
  for(const c of document.querySelectorAll('.card')){const f0=+c.dataset.f0,f1=+c.dataset.f1;
    tl.fromTo(c,{opacity:0,scale:1.05,filter:'blur(14px)'},{opacity:1,scale:1,filter:'blur(0px)',duration:5/FPS,ease:'power3.out',immediateRender:false},T(f0));
    tl.fromTo(c.querySelector('.rule'),{width:0},{width:120,duration:.5,ease:'power3.out',immediateRender:false},T(f0)+.05);
    const qs=[...c.querySelectorAll('.q')];
    qs.forEach((q,k)=>{const q0=+q.dataset.f0,q1=+q.dataset.f1;
      for(const w of q.querySelectorAll('.w'))tl.fromTo(w,{opacity:0,filter:'blur(14px)',y:12},{opacity:1,filter:'blur(0px)',y:0,duration:.24,ease:'power3.out',immediateRender:false},T(+w.dataset.f));
      if(k<qs.length-1){if(c.classList.contains('stack'))tl.to(q,{opacity:.36,duration:.22,ease:'power2.out'},T(q1)-.05);
        else tl.to(q,{opacity:0,y:-40,filter:'blur(12px)',duration:.18,ease:'power2.in'},T(q1)-.18);}});
    tl.to(c,{opacity:0,filter:'blur(10px)',duration:4/FPS,ease:'power2.in'},T(f1)-4/FPS);}
  // panneau « 3 posts »
  for(const p of document.querySelectorAll('.panel')){const f0=+p.dataset.f0,f1=+p.dataset.f1;
    tl.fromTo(p,{opacity:0,y:18,filter:'blur(8px)'},{opacity:1,y:0,filter:'blur(0px)',duration:.3,ease:'power3.out',immediateRender:false},T(f0));
    for(const l of p.querySelectorAll('.pl')){tl.fromTo(l,{opacity:0,x:-16},{opacity:1,x:0,duration:.22,ease:'power3.out',immediateRender:false},T(+l.dataset.f));
      tl.fromTo(l.querySelector('.sq'),{scale:0},{scale:1,duration:.25,ease:'back.out(3)',immediateRender:false},T(+l.dataset.f)+.04);
      const tg=l.querySelector('.ptag');tl.fromTo(tg,{opacity:0,x:10},{opacity:1,x:0,duration:.2,ease:'power3.out',immediateRender:false},T(+tg.dataset.f));}
    tl.to(p,{opacity:0,y:-10,filter:'blur(8px)',duration:.18,ease:'power2.in'},T(f1)-.18);}
  // listes qui défilent : l'élément actif est net, les autres flous
  for(const r of document.querySelectorAll('.wheel')){const f0=+r.dataset.f0,f1=+r.dataset.f1,pas=JSON.parse(r.dataset.pas),its=[...r.querySelectorAll('.it')],L=r.querySelector('.list');
    const etat=(k,dur,t)=>{tl.to(L,{y:-k*112,duration:dur,ease:'power3.inOut'},t);
      its.forEach((it,j)=>{const dd=Math.abs(j-k);tl.to(it,{opacity:dd===0?1:(dd===1?.26:0),filter:`blur(${dd?3+2*dd:0}px)`,duration:dur,ease:'power3.inOut'},t);});};
    tl.fromTo(r,{opacity:0,x:-20},{opacity:1,x:0,duration:.25,ease:'power3.out',immediateRender:false},T(f0));
    pas.forEach(([fr,k],i)=>etat(k,i?.22:.001,i?T(fr)-.12:T(f0)));
    const tg=r.querySelector('.wtag');if(tg){const k=+tg.dataset.item;tg.style.left=(104+its[k].offsetWidth+30)+'px';tg.style.top=(-tg.offsetHeight/2)+'px';
      tl.fromTo(tg,{opacity:0,y:10},{opacity:1,y:0,duration:.22,ease:'power3.out',immediateRender:false},T(+tg.dataset.f));}
    if(f1<NF)tl.to(r,{opacity:0,filter:'blur(8px)',duration:.15},T(f1)-.15);}
  // accroche épurée : avance lente (entière dès l'image 0) et brillance qui traverse le mot
  if(fx){tl.fromTo(fx.querySelector('.big'),{scale:1},{scale:1.05,duration:29/FPS,ease:'none'},0);
    tl.fromTo(fx.querySelectorAll('.big .w'),{'--sh':100},{'--sh':0,duration:.5,ease:'power2.inOut',immediateRender:false},T(8));}
  // tracés à la main : le trait se dessine, il suit l'élément qui le porte
  for(const [t,pa] of traces)tl.fromTo(pa,{strokeDashoffset:102},{strokeDashoffset:0,duration:t.df/FPS,ease:'power1.inOut',immediateRender:false},T(t.f0));
  // habillage : timecode, tête de lecture
  const tc=document.querySelector('.hud .tc span');
  if(tc)for(let fr=1;fr<NF;fr++){const s=Math.floor(fr/FPS),ff=fr%FPS;tl.set(tc,{innerText:`00:00:${String(s).padStart(2,'0')}:${String(ff).padStart(2,'0')}`},T(fr));}
  if(document.querySelector('.hud .head'))tl.fromTo('.hud .head',{x:0},{x:877,duration:D,ease:'none'},0);
  tl.set({},{},D);
  window.__timelines=window.__timelines||{};window.__timelines['main']=tl;
  if(window.__qaRapport)window.__qaRapport();
});
