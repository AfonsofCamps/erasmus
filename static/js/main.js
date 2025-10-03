
document.addEventListener('DOMContentLoaded', () => {
  gsap.from('.hero-title',{duration:0.8,y:-20,opacity:0});
  gsap.from('.card',{duration:0.6,stagger:0.1,y:10,opacity:0});
});
