import {useEffect,useState,type FormEvent} from 'react'
import {ArrowDownLeft,ArrowRight,ArrowUpRight,Check,Copy,Pencil,Plus,QrCode,Receipt,Trash2,Wallet} from 'lucide-react'
import confetti from 'canvas-confetti'
import {api,errorText} from './api'
import {Action,Dialog,Empty,Field,FormError,Notes,Panel,Pill,Select,number,options,value} from './ui'
import {categories,memberName,money,rupees,simplify,today,toPaise,type Cycle,type Data,type Expense,type Payment,type Summary,type Transfer,type Trip} from './types'

export type Mutate=(operation:()=>Promise<unknown>,message?:string)=>Promise<void>
export type Scope={cycle?:Cycle;trip?:Trip;all?:boolean}
export function SummaryCard({summary,member,trip}:{summary:Summary;member:number;trip?:Trip}){
  const mine=summary.balances.find(x=>x.member===member)
  const net=mine?.net??0
  return <section className="showcase">
    <div className="hero-icon"><Wallet size={22}/></div>
    <div className="showcase-main"><p>{trip?'Trip dividend':'Room dividend'}</p><strong className="amount">{money(summary.dividend)}</strong>
      <span>{money(summary.total)} shared by {summary.count} {trip?'travellers':'flatmates'}</span>
    </div>
    <div className="showcase-side"><div><p>Total paid by you</p><strong className="amount">{money(mine?.paid??0)}</strong></div>
      <div><p>{net>0?'You should receive':net<0?'You need to pay':'Your balance'}</p>
        <strong className={'amount '+(net>0?'positive':net<0?'negative':'')}>{net?money(Math.abs(net)):'Settled'} {net>0?<ArrowDownLeft size={16}/>:net<0?<ArrowUpRight size={16}/>:<Check size={16}/>}</strong>
      </div></div>
  </section>
}
export function BalanceRows({summary,data}:{summary:Summary;data:Data}){
  return <div className="rows">{summary.balances.map(row=><div className="row" key={row.member}><div className="grow"><strong>{memberName(data.members,row.member)}</strong><small>Paid {money(row.paid)} · Allocated {money(row.share)}</small></div><strong className={'amount '+(row.net>0?'green':row.net<0?'red':'')}>{row.net>0?'+':''}{money(row.net)}</strong></div>)}
    {!summary.balances.length&&<Empty>Balances appear when expenses are added.</Empty>}</div>
}
export function ExpenseRows({rows,data,edit,remove}:{rows:Expense[];data:Data;edit?:(item:Expense)=>void;remove?:(item:Expense)=>void}){
  return rows.length?<div className="rows">{rows.map(row=><div className="row" key={row.id}>
    <span className="row-icon"><Receipt size={17}/></span>
    <div className="grow"><strong>{row.title}</strong><small>{row.category} · {memberName(data.members,row.payer)} · {row.date}</small>{row.notes&&<small>{row.notes}</small>}</div>
    <strong className="amount">{money(row.paise)}</strong>
    {edit&&<button className="icon" aria-label={'Edit '+row.title} onClick={()=>edit(row)}><Pencil size={15}/></button>}
    {remove&&<button className="icon danger" aria-label={'Delete '+row.title} onClick={()=>remove(row)}><Trash2 size={15}/></button>}
  </div>)}</div>:<Empty>No expenses match this view.</Empty>
}
export function ExpenseDialog({data,scope,item,close,mutate}:{data:Data;scope:Scope;item?:Expense;close:()=>void;mutate:Mutate}){
  const [ledger,setLedger]=useState(item?.trip?'t'+item.trip:item?.cycle?'c'+item.cycle:scope.trip?'t'+scope.trip.id:'c'+(scope.cycle?.id??data.cycles.find(c=>c.status==='ACTIVE')?.id??''))
  const [split,setSplit]=useState(item?.split_type??'EQUAL')
  const [selected,setSelected]=useState<number[]|null>(item?.splits.map(s=>s.member)??null)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const trip=data.trips.find(t=>'t'+t.id===ledger)
  const cycle=data.cycles.find(c=>'c'+c.id===ledger)
  const eligible=data.members.filter(m=>{
    if(item?.payer===m.id||item?.splits.some(s=>s.member===m.id)) return true
    return m.active && (trip?trip.participants.includes(m.id):!m.is_trip_guest && (!cycle?.archived_members.length||cycle.archived_members.includes(m.id)))
  })
  const chosen=selected??eligible.map(m=>m.id)
  const defaultDate=trip?(today()>=trip.start&&today()<=trip.end?today():trip.start):cycle&&!today().startsWith(cycle.month)?cycle.month+'-01':today()
  async function save(event:FormEvent<HTMLFormElement>){
    event.preventDefault();setBusy(true);setError('')
    const form=new FormData(event.currentTarget)
    try{
      const payload={title:value(form,'title'),paise:toPaise(value(form,'amount')),category:value(form,'category'),notes:value(form,'notes'),
        date:value(form,'date'),payer:number(form,'payer'),trip:trip?.id??null,cycle:cycle?.id??null,
        frequency:trip?'':value(form,'frequency'),split_type:split,
        splits:chosen.map(member=>({member,value:split==='EQUAL'?'1':value(form,'share-'+member)}))}
      await mutate(()=>item?api.patch('/expenses/'+item.id+'/',payload):api.post('/expenses/',payload),item?'Expense updated':'Expense added')
      close()
    }catch(problem){setError(errorText(problem))}
    finally{setBusy(false)}
  }
  return <Dialog title={item?'Edit expense':'Add expense'} close={close}><form onSubmit={save} className="form">
    <Field label="Expense title" name="title" value={item?.title}/>
    {!item&&<Select label="Ledger" name="ledger" value={ledger} onChange={key=>{setLedger(key);setSelected(null)}} options={[
      ...data.cycles.filter(c=>c.status==='ACTIVE').map(c=>({value:'c'+c.id,label:'Flat · '+c.month})),
      ...data.trips.map(t=>({value:'t'+t.id,label:'Trip · '+t.name}))
    ]}/>}
    <div className="form-grid"><Field label="Amount (₹)" name="amount" type="number" step=".01" min={0.01} value={item?rupees(item.paise):undefined}/>
      <Select label="Category" name="category" value={item?.category??(trip?'Trip':'Groceries')} options={categories.map(v=>({value:v,label:v}))}/>
      <Select key={ledger} label="Paid by" name="payer" value={item?.payer} options={eligible.map(m=>({value:m.id,label:m.name}))}/>
      <Field key={ledger+'date'} label="Date" name="date" type="date" value={item?.date??defaultDate}/>
      <Select label="Split method" name="split" value={split} onChange={setSplit} options={options(['EQUAL','EXACT','PERCENT','SHARES'])}/>
      {!trip&&<Select label="Repeat" name="frequency" required={false} value={item?.frequency??''} options={[{value:'',label:'One time'},...options(['WEEKLY','BIWEEKLY','MONTHLY'])]}/>}
    </div>
    <fieldset><legend>Split participants {split==='EXACT'?'· ₹':split==='PERCENT'?'· %':split==='SHARES'?'· shares':''}</legend>
      {eligible.map(m=><div className="split-row" key={m.id}>
        <label><input type="checkbox" checked={chosen.includes(m.id)} onChange={event=>setSelected(event.target.checked?[...chosen,m.id]:chosen.filter(id=>id!==m.id))}/> {m.name}</label>
        {split!=='EQUAL'&&chosen.includes(m.id)&&<Field key={split} label={m.name+' allocation'} type="number" min={0} step={split==='EXACT'?'.01':'.0001'} name={'share-'+m.id} value={item?.split_type===split?item.splits.find(s=>s.member===m.id)?.value:split==='SHARES'?1:undefined}/>}
      </div>)}
    </fieldset>
    <Notes value={item?.notes}/><FormError message={error}/><button className="primary" disabled={busy||!chosen.length||(!cycle&&!trip)}>{busy?'Saving…':'Save expense'}</button>
  </form></Dialog>
}

export function PaymentDialog({data,scope,transfer,pending,close,mutate}:{data:Data;scope:Scope;transfer:Transfer;pending?:Payment;close:()=>void;mutate:Mutate}){
  const receiver=data.members.find(m=>m.id===transfer.receiver)
  const link=receiver?.upi?'upi://pay?'+new URLSearchParams({pa:receiver.upi,pn:receiver.name,am:rupees(transfer.paise),cu:'INR',tn:'BroShare settlement'}).toString():''
  const [qr,setQr]=useState<{size:number;path:string}|null>(null)
  const [error,setError]=useState('')
  const [busy,setBusy]=useState(false)
  const [copied,setCopied]=useState('')
  const [key]=useState(()=>crypto.randomUUID())
  useEffect(()=>{
    if(!link)return
    const controller=new AbortController()
    api.post('/payment-qr/',{receiver:transfer.receiver,paise:transfer.paise},{signal:controller.signal})
      .then(({data})=>setQr(data)).catch(()=>{if(!controller.signal.aborted)setError('The QR code could not be generated.')})
    return ()=>controller.abort()
  },[link,transfer.receiver,transfer.paise])
  async function copy(text:string,label:string){
    try{await navigator.clipboard.writeText(text);setCopied(label+' copied')}
    catch{setError('Clipboard access is unavailable. Select and copy the UPI ID manually.')}
  }
  async function save(event:FormEvent<HTMLFormElement>){
    event.preventDefault();setBusy(true);setError('')
    const form=new FormData(event.currentTarget)
    const details={method:value(form,'method'),reference:value(form,'reference'),notes:value(form,'notes')}
    try{
      await mutate(()=>pending?api.post('/settlements/'+pending.id+'/confirm/',details):api.post('/settlements/',{
        ...details,...transfer,cycle:scope.cycle?.id??null,trip:scope.trip?.id??null,request_key:key,
      }),'Payment recorded')
      if(!matchMedia('(prefers-reduced-motion: reduce)').matches) confetti({particleCount:65,spread:55,origin:{y:.7}})
      close()
    }catch(problem){setError(errorText(problem))}
    finally{setBusy(false)}
  }
  return <Dialog title="Record settlement" close={close}><div className="payment-summary"><span>{memberName(data.members,transfer.payer)} → {receiver?.name}</span><strong className="amount">{money(transfer.paise)}</strong></div>
    {link&&<div className="qr"><div>{qr&&<svg width="140" height="140" viewBox={`0 0 ${qr.size} ${qr.size}`} role="img" aria-label="Scan this QR code in a UPI app" shapeRendering="crispEdges"><rect width={qr.size} height={qr.size} fill="white"/><path d={qr.path} fill="black"/></svg>}</div><div><strong>{receiver?.upi}</strong>
      <div className="actions"><a className="secondary" href={link}><QrCode size={15}/> Pay via UPI</a><button className="secondary" onClick={()=>void copy(receiver!.upi,'UPI ID')}><Copy size={15}/> Copy ID</button><button className="secondary" onClick={()=>void copy(link,'Link')}>Copy link</button></div><small role="status">{copied||'Record the payment after completing it externally.'}</small></div></div>}
    <form className="form" onSubmit={save}><div className="form-grid"><Select label="Payment method" name="method" options={options(['UPI','CASH','BANK'])}/><Field label="Reference / UTR" name="reference" required={false} maxLength={100}/></div>
      <Notes/><FormError message={error}/><button className="primary" disabled={busy}>{busy?'Recording…':'Confirm payment recorded'}</button></form>
  </Dialog>
}
export function SettlementRows({data,summary,canPay,onPay}:{data:Data;summary:Summary;canPay:boolean;onPay:(transfer:Transfer)=>void}){
  const computed=simplify(summary.balances)
  const transfers=JSON.stringify(computed)===JSON.stringify(summary.transfers)?computed:summary.transfers
  if(!transfers.length) return <Empty>Everyone is settled up.</Empty>
  return <div className="rows">{transfers.map(row=><div className="row" key={row.payer+'-'+row.receiver}>
    <span className="row-icon"><ArrowRight size={17}/></span><div className="grow"><strong>{memberName(data.members,row.payer)} → {memberName(data.members,row.receiver)}</strong>
    <small>{data.members.find(m=>m.id===row.receiver)?.upi||'No UPI ID'}</small></div><strong className="amount">{money(row.paise)}</strong>
    {canPay&&<button className="secondary" onClick={()=>onPay(row)}>Settle up</button>}
  </div>)}</div>
}
export function History({payments,data,confirm,reverse}:{payments:Payment[];data:Data;confirm?:(item:Payment)=>void;reverse?:(item:Payment)=>void}){
  return payments.length?<div className="rows">{payments.map(row=><div className="row" key={row.id}><div className="grow">
    <strong>{memberName(data.members,row.payer)} → {memberName(data.members,row.receiver)}</strong>
    <small>{row.date} · {row.method}{row.reference?' · '+row.reference:''}</small>{row.notes&&<small>{row.notes}</small>}</div>
    <Pill tone={row.status==='CONFIRMED'?'green':row.status==='PENDING'?'amber':''}>{row.status}</Pill><strong className="amount">{money(row.paise)}</strong>
    {confirm&&row.status==='PENDING'&&<button className="secondary" onClick={()=>confirm(row)}>Record</button>}
    {reverse&&row.status!=='REVERSED'&&<button className="icon danger" aria-label="Reverse settlement" onClick={()=>reverse(row)}><Trash2 size={15}/></button>}
  </div>)}</div>:<Empty>No settlement records yet.</Empty>
}
export function BillingDialog({cycle,summary,data,close,mutate,choose}:{
  cycle:Cycle;summary:Summary;data:Data;close:()=>void;mutate:Mutate;choose:(id:number)=>void
}){
  const [error,setError]=useState('')
  const [busy,setBusy]=useState(false)
  async function save(event:FormEvent<HTMLFormElement>){
    event.preventDefault();setBusy(true);setError('')
    const form=new FormData(event.currentTarget)
    try{
      let id=cycle.id
      await mutate(async()=>{const {data}=await api.post('/billing-cycle/settle-month/',{cycle:cycle.id,rollover:form.has('rollover')});id=data.cycle},'Next month opened')
      choose(id);close()
    } catch(problem){setError(errorText(problem))}
    finally{setBusy(false)}
  }
  return <Dialog title={'Close '+cycle.month+' and open next month'} close={close}><form className="form" onSubmit={save}>
    <p>{money(summary.total)} spent · {summary.count} flatmates · {money(summary.dividend)} dividend</p>
    <BalanceRows summary={summary} data={data}/><SettlementRows summary={summary} data={data} canPay={false} onPay={()=>undefined}/>
    <p className="muted">Transfers are saved as pending for the first day of the next month. Confirm them after payment.</p>
    <label className="check"><input type="checkbox" name="rollover" defaultChecked/> Generate recurring bills due on the first</label>
    <FormError message={error}/><button className="primary" disabled={busy}>{busy?'Closing cycle…':'Close cycle and open next month'}</button>
  </form></Dialog>
}
export function Filters({data,rows,onEdit,onDelete,onAdd}:{data:Data;rows:Expense[];onEdit:(x:Expense)=>void;onDelete:(x:Expense)=>void;onAdd:()=>void}){
  const [filters,set]=useState({search:'',scope:'',cycle:'',trip:'',category:'',payer:''})
  const choices=(label:string,items:{value:string|number;label:string}[])=>[{value:'',label},...items]
  const change=(key:keyof typeof filters)=>(val:string)=>set(prior=>({...prior,[key]:val}))
  const shown=rows.filter(x=>(!filters.search||[x.title,x.notes].some(s=>s.toLowerCase().includes(filters.search.toLowerCase())))&&
    (!filters.scope||(filters.scope==='trip'?Boolean(x.trip):!x.trip))&&(!filters.cycle||String(x.cycle)===filters.cycle)&&
    (!filters.trip||String(x.trip)===filters.trip)&&(!filters.category||x.category===filters.category)&&(!filters.payer||String(x.payer)===filters.payer))
  return <Panel title="All expenses" action={<Action onClick={onAdd}><Plus size={17}/> Add expense</Action>}>
    <div className="filters"><label className="field">Search<input placeholder="Search expenses" value={filters.search} onChange={e=>change('search')(e.target.value)}/></label>
      <Select label="Scope" name="scope" required={false} options={choices('All ledgers',[{value:'room',label:'Flat'},{value:'trip',label:'Trips'}])} onChange={change('scope')}/>
      <Select label="Billing month" name="cycle" required={false} options={choices('All months',data.cycles.map(x=>({value:x.id,label:x.month})))} onChange={change('cycle')}/>
      <Select label="Trip" name="trip" required={false} options={choices('All trips',data.trips.map(x=>({value:x.id,label:x.name})))} onChange={change('trip')}/>
      <Select label="Category" name="category" required={false} options={choices('All categories',categories.map(x=>({value:x,label:x})))} onChange={change('category')}/>
      <Select label="Payer" name="payer" required={false} options={choices('All payers',data.members.map(x=>({value:x.id,label:x.name})))} onChange={change('payer')}/>
    </div>
    <ExpenseRows rows={shown} data={data} edit={onEdit} remove={onDelete}/>
  </Panel>
}


