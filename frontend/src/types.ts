export type Member={id:number;name:string;role:string;upi:string;color:string;active:boolean;is_trip_guest:boolean;user:number|null}
export type Cycle={id:number;month:string;status:string;archived_members:number[]}
export type Trip={id:number;name:string;destination:string;start:string;end:string;budget:number;status:string;participants:number[]}
export type Split={member:number;value:string;paise:number}
export type Expense={id:number;title:string;paise:number;category:string;date:string;notes:string;payer:number;trip:number|null;cycle:number|null;split_type:string;splits:Split[];frequency:string}
export type Transfer={payer:number;receiver:number;paise:number}
export type Payment=Transfer&{id:number;cycle:number|null;trip:number|null;method:string;reference:string;notes:string;date:string;status:string}
export type Balance={member:number;paid:number;share:number;net:number}
export type Summary={total:number;count:number;dividend:number;balances:Balance[];transfers:Transfer[];pending:number}
export type Chore={id:number;title:string;assigned:number;frequency:string;points:number;due:string;active:boolean;logs:{id:number;member:number;created_at:string;points:number}[]}
export type Issue={id:number;title:string;notes:string;technician:string;priority:string;status:string;estimated:number;actual:number;resolved:string|null;reported_by:number;expense:number|null}
export type Reminder={id:number;title:string;notes:string;kind:string;read:boolean;created_at:string}
export type Data={members:Member[];cycles:Cycle[];trips:Trip[];expenses:Expense[];payments:Payment[];chores:Chore[];issues:Issue[];reminders:Reminder[]}
export const categories=['Rent','Groceries','Electricity','Wi-Fi & Internet','Cook & Maid','Water & Gas','Household Supplies','Food & Dining','Entertainment','Maintenance','Trip','Other']
export const money=(paise:number)=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',minimumFractionDigits:paise%100?2:0}).format(paise/100)
export const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kolkata',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())
export const memberName=(members:Member[],id:number)=>members.find(m=>m.id===id)?.name ?? 'Former member'
export const rupees=(paise:number)=>(paise/100).toFixed(2)
export function toPaise(input:string){
  if(!/^\d+(\.\d{0,2})?$/.test(input)) throw new Error('Enter an amount in rupees with up to two decimal places.')
  const [whole,fraction='']=input.split('.')
  const value=Number(whole)*100+Number(fraction.padEnd(2,'0'))
  if(!Number.isSafeInteger(value) || value>2147483647) throw new Error('Enter a smaller amount.')
  return value
}
export function simplify(balances:Balance[]):Transfer[]{
  const outstanding=new Map(balances.map(x=>[x.member,x.net]))
  const transfers:Transfer[]=[]
  while(true){
    const sorted=[...outstanding].sort(([a,av],[b,bv])=>bv-av||a-b)
    const creditor=sorted.find(([,amount])=>amount>0)
    const debtor=sorted.filter(([,amount])=>amount<0).sort(([a,av],[b,bv])=>av-bv||a-b)[0]
    if(!creditor||!debtor) return transfers
    const paise=Math.min(creditor[1],-debtor[1])
    outstanding.set(creditor[0],creditor[1]-paise)
    outstanding.set(debtor[0],debtor[1]+paise)
    transfers.push({payer:debtor[0],receiver:creditor[0],paise})
  }
}

