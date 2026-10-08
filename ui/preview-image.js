/* A view-only image: source identifiers and scope travel with the pixels. */
function previewImageCanvas(source, paragraphs) {
  const output=document.createElement('canvas'),width=Math.max(320,source.width),padding=16,lineHeight=21;
  const context=output.getContext('2d');context.font='14px sans-serif';
  const lines=[];
  for(const paragraph of paragraphs){
    let line='';
    for(const word of String(paragraph).split(' ')){
      if(line&&context.measureText(line+' '+word).width>width-2*padding){lines.push(line);line='';}
      if(line)line+=' ';
      for(const character of word){
        if(context.measureText(line+character).width>width-2*padding&&line){lines.push(line);line='';}
        line+=character;
      }
    }
    lines.push(line);
  }
  output.width=width;output.height=source.height+padding*2+lines.length*lineHeight;
  context.fillStyle='#fffef9';context.fillRect(0,0,output.width,output.height);
  context.drawImage(source,Math.floor((width-source.width)/2),0);
  context.font='14px sans-serif';context.fillStyle='#21332d';
  lines.forEach((line,i)=>context.fillText(line,padding,source.height+padding+16+i*lineHeight));
  return output;
}
