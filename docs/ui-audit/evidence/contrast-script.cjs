const hex=h=>h.replace('#','').match(/../g).map(x=>parseInt(x,16)/255);
const lin=c=>c<=0.03928?c/12.92:Math.pow((c+0.055)/1.055,2.4);
const L=h=>{const [r,g,b]=hex(h).map(lin);return 0.2126*r+0.7152*g+0.0722*b};
const cr=(a,b)=>{const [x,y]=[L(a),L(b)].sort((p,q)=>q-p);return (x+0.05)/(y+0.05)};
const c={canvas:'#fafaf9',surface:'#f5f5f4',raised:'#e7e5e4',line:'#d6d3d1',ink:'#1c1917',soft:'#57534e',mute:'#78716c',ok:'#16a34a',warn:'#d97706',danger:'#dc2626',ember:'#c2410c'};
const pairs=[['line','canvas'],['line','surface'],['warn','surface'],['ok','surface'],['danger','surface'],['mute','surface'],['mute','raised'],['ink','canvas'],['soft','surface'],['ember','canvas'],['mute','canvas']];
for(const [a,b] of pairs) console.log((a+'/'+b).padEnd(16), cr(c[a],c[b]).toFixed(2));
