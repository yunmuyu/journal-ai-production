// Call only for a source-identified electrical label. Quantity resolves shorthand;
// net names and part identifiers are deliberately outside this formatter.
export function electricalLabel(text,quantity){
 const explicit=text.match(/^([+-]?\d+(?:\.\d+)?)\s*(kΩ|MΩ|Ω|[kMG]?Hz|[munpμµ]?F|[munpμµ]?f|[munpμµ]?A|[munpμµ]?V)$/);
 if(explicit)return explicit[1]+' '+explicit[2].replace(/[uµ]/,'μ').replace(/f$/,'F');
 const short=text.match(/^([+-]?\d+(?:\.\d+)?)\s*([kKMmunp])$/);if(!short)return text;
 const unit=quantity==='resistance'?{k:'kΩ',K:'kΩ',M:'MΩ'}:quantity==='frequency'?{k:'kHz',K:'kHz',M:'MHz'}:quantity==='capacitance'?{u:'μF',n:'nF',p:'pF'}:{};
 return unit[short[2]]?short[1]+' '+unit[short[2]]:text;
}
