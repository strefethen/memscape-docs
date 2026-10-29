
export function civil_parts(instant,zone) {
 const date=new Date(instant); if(!Number.isFinite(date.getTime())) throw new Error('Invalid clock instant');
 const parts=new Intl.DateTimeFormat('en-US-u-ca-gregory-nu-latn',{calendar:'gregory',numberingSystem:'latn',timeZone:zone,year:'numeric',month:'numeric',day:'numeric'}).formatToParts(date);
 const read=k=>{const p=parts.find(p=>p.type===k);if(!p || !/^\d+$/.test(p.value)) throw new Error('Missing Gregorian '+k);return Number(p.value)};
 return [read('year'),read('month'),read('day')];
}
export function current_clock() {
 const options=new Intl.DateTimeFormat().resolvedOptions();
 if(!options.timeZone || !options.locale) throw new Error('Browser locale/time zone missing');
 const locale=new Intl.Locale(options.locale);
 const week=typeof locale.getWeekInfo==='function'?locale.getWeekInfo():locale.weekInfo;
 if(!week || !Number.isInteger(week.firstDay)) throw new Error('Locale week information unavailable');
 return [...civil_parts(new Date().getTime(),options.timeZone),week.firstDay,options.timeZone,options.locale];
}
export function next_clock_delay() {
 const now=new Date(); const next=new Date(now.getFullYear(),now.getMonth(),now.getDate()+1);
 const delta=next.getTime()-now.getTime(); if(!Number.isFinite(delta)||delta<=0) throw new Error('Cannot schedule local midnight');
 return Math.min(60000,delta+10);
}
