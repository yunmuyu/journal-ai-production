import * as pdfjs from '/pdfjs/pdf.mjs';
pdfjs.GlobalWorkerOptions.workerSrc='/pdfjs/pdf.worker.mjs';
const token=location.pathname.split('/')[2];
const download=document.getElementById('download');download.href='/file/'+token;
try{
 const pdf=await pdfjs.getDocument({url:download.href,standardFontDataUrl:'/pdfjs/fonts/'}).promise;
 for(let n=1;n<=pdf.numPages;n++){
  const page=await pdf.getPage(n),viewport=page.getViewport({scale:2});const canvas=document.createElement('canvas');canvas.width=viewport.width;canvas.height=viewport.height;canvas.setAttribute('aria-label','PDF第'+n+'页');document.getElementById('pages').append(canvas);await page.render({canvasContext:canvas.getContext('2d'),viewport}).promise;
 }
 document.getElementById('message').textContent='原PDF · '+pdf.numPages+'页';
}catch(error){document.getElementById('message').textContent='预览失败，请下载原PDF：'+error.message;}
