'use strict';
// Presentation-only enhancements. All model calculations stay in app.js and the API.
(() => {
 const address=document.querySelector('#local-address');
 if(address)address.textContent=location.host;
 const links=[...document.querySelectorAll('.sidebar-nav a')];
 const sections=links.map(a=>document.querySelector(a.getAttribute('href'))).filter(Boolean);
 let scheduled=false;
 function highlight(){
  scheduled=false;
  let active=sections[0];
  for(const section of sections){if(!section.hidden&&section.getBoundingClientRect().top<=160)active=section;}
  for(const a of links){const on=a.getAttribute('href')==='#'+active.id;a.classList.toggle('active',on);if(on)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current');}
 }
 addEventListener('scroll',()=>{if(!scheduled){scheduled=true;requestAnimationFrame(highlight);}},{passive:true});
 const results=document.querySelector('#results'),resultsNav=document.querySelector('#results-nav');
 new MutationObserver(()=>{resultsNav.hidden=results.hidden;highlight();}).observe(results,{attributes:true,attributeFilter:['hidden']});
 const status=document.querySelector('#status'),label=document.querySelector('#engine-label');
 new MutationObserver(()=>{const active=status.classList.contains('busy');label.textContent=active?'正在本机计算':status.classList.contains('error')?'请检查输入':'本地引擎就绪';label.parentElement.classList.toggle('engine-busy',active);}).observe(status,{attributes:true,childList:true,subtree:true});
 highlight();
})();
