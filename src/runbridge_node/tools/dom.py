"""项目固定 DOM 采集脚本；参数不作为调用方脚本执行。"""

INSPECT = """selector => ({url:location.href,elements:Array.from(document.querySelectorAll(selector)).slice(0,200).map(el=>({tag:el.tagName.toLowerCase(),attributes:Object.fromEntries(Array.from(el.attributes,a=>[a.name,a.value])),text:el.textContent?.trim().slice(0,2000)})),truncated:document.querySelectorAll(selector).length>200})"""

CAPTURE = r"""({captures, origins}) => {
  if (!origins.includes(location.origin)) throw new Error('CAPTURE_OUTSIDE_ORIGIN');
  const values={};
  for (const [name,c] of Object.entries(captures)) {
    if(c.mode==='url'){values[name]=c.field==='pathname'?location.pathname:location.href;continue;}
    const nodes=document.querySelectorAll(c.selector), el=nodes[c.index??0];
    if(c.mode==='count'){values[name]=nodes.length;continue;}
    if(c.mode==='visible'){values[name]=!!el&&!!el.getClientRects().length;continue;}
    if(!el)continue;
    if(c.index===undefined&&nodes.length!==1)throw new Error('AMBIGUOUS_CAPTURE');
    if(c.mode==='value'){values[name]=el.value;continue;}
    let text=(c.attribute?el.getAttribute(c.attribute):el.textContent)?.trim();
    if(c.field==='pathname'&&c.attribute==='href'&&text)text=new URL(text,location.href).pathname;
    if(c.mode==='number'){
      if(text===undefined||text===null||!/^\d+(?:\.\d+)?$/.test(text.replaceAll(',','')))throw new Error('INVALID_CAPTURE_NUMBER');
      values[name]=Number(text.replaceAll(',',''));
    }else if(c.mode==='attribute'){if(text!==null&&text!==undefined)values[name]=text;}
    else values[name]=text;
  }
  return {values,url:location.href,title:document.title,truncated:false};
}"""
