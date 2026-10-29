
export function calendar_weekdays(locale,first) {const format=new Intl.DateTimeFormat(locale,{calendar:'gregory',timeZone:'UTC',weekday:'short'});return Array.from({length:7},(_,i)=>format.format(new Date(Date.UTC(2001,0,1+(first-1+i)%7))));}
export function calendar_day_label(y,m,d,locale) {const date=new Date(0);date.setUTCFullYear(y,m-1,d);return new Intl.DateTimeFormat(locale,{calendar:'gregory',timeZone:'UTC',weekday:'long',year:'numeric',month:'long',day:'numeric'}).format(date);}
