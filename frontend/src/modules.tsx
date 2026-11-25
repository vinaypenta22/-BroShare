import {useEffect,useState,type FormEvent,type ReactNode} from 'react'
import {Bar,BarChart,CartesianGrid,ResponsiveContainer,Tooltip,XAxis,YAxis} from 'recharts'
import {Bell,Check,ChevronRight,ClipboardList,Download,Pencil,Plus,Trash2,UserRound,Users,Wrench} from 'lucide-react'
import {api,errorText,type Profile} from './api'
import {History,type Mutate} from './finance'
import {Action,Dialog,Empty,Field,FormError,Notes,Panel,Pill,Select,number,options,value} from './ui'
import {memberName,money,rupees,today,toPaise,type Chore,type Data,type Issue,type Member,type Trip} from './types'

export type Modal={title:string;body:ReactNode;submit:(form:FormData)=>Promise<void>;label?:string}
export function FormDialog({modal,close}:{modal:Modal;close:()=>void}){
  const [error,setError]=useState('')
  const [busy,setBusy]=useState(false)
  async function save(event:FormEvent<HTMLFormElement>){
    event.preventDefault();setBusy(true);setError('')
    try{await modal.submit(new FormData(event.currentTarget));close()}
    catch(problem){setError(errorText(problem))}
    finally{setBusy(false)}
  }
  return <Dialog title={modal.title} close={close}><form className="form" onSubmit={save}>{modal.body}
    <FormError message={error}/><button className="primary" disabled={busy}>{busy?'Working…':modal.label??'Save changes'}</button>
  </form></Dialog>
}
type Props={data:Data;mutate:Mutate;show:(m:Modal)=>void;lead:boolean}
const selected=(data:Data)=>data.members.filter(m=>m.active&&!m.is_trip_guest)
const memberOptions=(data:Data)=>selected(data).map(m=>({value:m.id,label:m.name}))

export function Members({data,mutate,show,lead}:{data:Data;mutate:Mutate;show:(m:Modal)=>void;lead:boolean}){
  function edit(member?:Member){
    show({title:member?'Edit flatmate':'Add flatmate',body:<>
      <Field label="Name" name="name" value={member?.name}/>
      <Field label="UPI ID" name="upi" value={member?.upi} required={false}/>
      <Select label="Role" name="role" value={member?.role} options={[{value:'MEMBER',label:'Flatmate'},{value:'LEAD',label:'Flat lead'}]}/>
    </>,submit:form=>mutate(()=>api.request({url:'/roommates/'+(member?member.id+'/':''),method:member?'PATCH':'POST',data:{name:value(form,'name'),upi:value(form,'upi'),role:value(form,'role')}}),'Directory updated')})
  }
  return <Panel title="Flatmates" action={lead&&<Action onClick={()=>edit()}><Plus size={17}/> Add flatmate</Action>}>
    <div className="rows">{data.members.filter(m=>!m.is_trip_guest).map(m=><div className="row" key={m.id}>
      <span className="avatar" style={{background:m.color}}>{m.name.slice(0,2).toUpperCase()}</span><div className="grow"><strong>{m.name}</strong><small>{m.upi||'No UPI ID'}</small></div>
      <Pill tone={!m.active?'':m.role==='LEAD'?'green':''}>{!m.active?'Archived':m.role==='LEAD'?'Flat lead':'Flatmate'}</Pill>
      {lead&&m.active&&<><button className="icon" aria-label={'Edit '+m.name} onClick={()=>edit(m)}><Pencil size={15}/></button>
      <button className="icon danger" aria-label={'Archive '+m.name} onClick={()=>show({title:'Archive '+m.name,body:<p>Their expense and payment history stays in this flat.</p>,label:'Archive flatmate',submit:()=>mutate(()=>api.delete('/roommates/'+m.id+'/'),'Flatmate archived')})}><Trash2 size={15}/></button></>}
      {lead&&!m.active&&<button className="secondary" onClick={()=>show({title:'Restore '+m.name,body:<p>Restore this person to the active flatmate directory.</p>,label:'Restore flatmate',submit:()=>mutate(()=>api.post('/roommates/'+m.id+'/restore/'),'Flatmate restored')})}>Restore</button>}
    </div>)}</div>
  </Panel>
}
export function Trips({data,mutate,show,lead,choose,active}:Props&{choose:(id:number)=>void;active?:Trip}){
  function edit(trip?:Trip){
    show({title:trip?'Edit trip':'Create trip',body:<>
      <Field label="Trip name" name="name" value={trip?.name}/><Field label="Destination" name="destination" value={trip?.destination}/>
      <div className="form-grid"><Field label="Start date" name="start" type="date" value={trip?.start??today()}/><Field label="End date" name="end" type="date" value={trip?.end??today()}/>
      <Field label="Budget (₹)" name="budget" type="number" min={0} step=".01" value={rupees(trip?.budget??0)}/><Select label="Status" name="status" options={options(['PLANNED','ACTIVE','COMPLETED'])} value={trip?.status}/></div>
      <fieldset><legend>Travellers</legend>{data.members.filter(m=>m.active||trip?.participants.includes(m.id)).map(m=><label className="check" key={m.id}><input type="checkbox" name="participants" value={m.id} defaultChecked={trip?.participants.includes(m.id)??false}/>{m.name}{m.is_trip_guest?' · Guest':''}</label>)}</fieldset>
    </>,label:trip?'Save trip':'Create trip',submit:async form=>{
      const payload={name:value(form,'name'),destination:value(form,'destination'),start:value(form,'start'),end:value(form,'end'),budget:toPaise(value(form,'budget')),
        status:value(form,'status'),participants:form.getAll('participants').map(Number)}
      await mutate(async()=>{const {data:result}=await api.request<Trip>({url:'/trips/'+(trip?trip.id+'/':''),method:trip?'PATCH':'POST',data:payload});choose(result.id)},'Trip saved')
    }})
  }
  return <Panel title="Group trips" action={<div className="actions">
    <button className="secondary" onClick={()=>show({title:'Add external guest',body:<><Field label="Guest name" name="name"/><Field label="UPI ID" name="upi" required={false}/></>,
      label:'Add guest',submit:async form=>{
        await mutate(()=>api.post<Member>('/roommates/guest/',{name:value(form,'name'),upi:value(form,'upi'),trip:active?.id}),active?'Guest added to trip':'Guest added to traveller directory')
      }})}><Users size={16}/> Add guest</button>
    <Action onClick={()=>edit()}><Plus size={17}/> Create trip</Action></div>}>
    {data.trips.length?<div className="rows">{data.trips.map(t=><div className={'row '+(active?.id===t.id?'selected-row':'')} key={t.id}>
      <button className="row-link grow" onClick={()=>choose(t.id)}><strong>{t.name}</strong><small>{t.destination} · {t.start} to {t.end} · {t.participants.length} travellers</small></button>
      <Pill>{t.status}</Pill><button className="icon" aria-label={'Edit '+t.name} onClick={()=>edit(t)}><Pencil size={15}/></button>
      {lead&&<button className="icon danger" aria-label={'Archive '+t.name} onClick={()=>show({title:'Archive '+t.name,body:<p>The trip and its financial history stay in your backup.</p>,label:'Archive trip',submit:()=>mutate(()=>api.delete('/trips/'+t.id+'/'),'Trip archived')})}><Trash2 size={15}/></button>}
      <button className="icon" aria-label={'Open '+t.name} onClick={()=>choose(t.id)}><ChevronRight size={17}/></button>
    </div>)}</div>:<Empty>Create a trip to start tracking travel expenses.</Empty>}
  </Panel>
}
export function Chores({data,mutate,show}:Props){
  function edit(chore?:Chore){
    show({title:chore?'Edit chore':'Add chore',body:<><Field label="Chore name" name="title" value={chore?.title}/>
      <Select label="Assigned to" name="assigned" value={chore?.assigned} options={memberOptions(data)}/>
      <div className="form-grid"><Select label="Frequency" name="frequency" value={chore?.frequency} options={options(['DAILY','WEEKLY','BIWEEKLY','MONTHLY'])}/>
      <Field label="Due date" name="due" type="date" value={chore?.due??today()}/><Field label="Fairness points" name="points" type="number" min={1} value={chore?.points??1}/></div></>,
      submit:form=>mutate(()=>api.request({url:'/chores/'+(chore?chore.id+'/':''),method:chore?'PATCH':'POST',data:{
        title:value(form,'title'),assigned:number(form,'assigned'),frequency:value(form,'frequency'),due:value(form,'due'),points:number(form,'points')
      }}),'Chore saved')})
  }
  const history=data.chores.flatMap(c=>c.logs.map(log=>({...log,title:c.title}))).sort((a,b)=>b.created_at.localeCompare(a.created_at))
  return <div className="stack"><Panel title="Chore rotation" action={<Action onClick={()=>edit()}><Plus size={17}/> Add chore</Action>}>
    {data.chores.some(c=>c.active)?<div className="rows">{data.chores.filter(c=>c.active).map(c=><div className="row" key={c.id}>
      <span className="row-icon"><ClipboardList size={17}/></span><div className="grow"><strong>{c.title}</strong><small>{memberName(data.members,c.assigned)} · {c.due} · {c.frequency.toLowerCase()} · {c.points} pts</small></div>
      {c.due<today()&&<Pill tone="amber">Overdue</Pill>}
      <button className="secondary" onClick={()=>show({title:'Complete '+c.title,body:<p>Credit {c.points} points to {memberName(data.members,c.assigned)} and rotate the next assignment.</p>,label:'Complete chore',submit:()=>mutate(()=>api.post('/chores/'+c.id+'/complete/',{due:c.due}),'Chore completed')})}><Check size={15}/> Done</button>
      <button className="secondary" onClick={()=>show({title:'Swap assignment',body:<Select label="Assign to" name="assigned" value={c.assigned} options={memberOptions(data)}/>,submit:form=>mutate(()=>api.post('/chores/'+c.id+'/swap/',{member:number(form,'assigned')}),'Assignment updated')})}>Swap</button>
      <button className="icon" aria-label={'Edit '+c.title} onClick={()=>edit(c)}><Pencil size={15}/></button>
      <button className="icon danger" aria-label={'Archive '+c.title} onClick={()=>show({title:'Archive '+c.title,body:<p>Previous completions remain in chore history.</p>,label:'Archive chore',submit:()=>mutate(()=>api.delete('/chores/'+c.id+'/'),'Chore archived')})}><Trash2 size={15}/></button>
    </div>)}</div>:<Empty>Add a chore to start rotating responsibilities.</Empty>}
  </Panel><div className="two-col"><Panel title="Fairness points">{selected(data).map(m=><div className="row" key={m.id}><span className="grow">{m.name}</span><strong>{history.filter(h=>h.member===m.id).reduce((n,h)=>n+h.points,0)} pts</strong></div>)}</Panel>
  <Panel title="Completion history">{history.length?history.map(h=><div className="row" key={h.id}><div className="grow"><strong>{h.title}</strong><small>{memberName(data.members,h.member)} · {h.created_at.slice(0,10)}</small></div><Pill tone="green">+{h.points} pts</Pill></div>):<Empty>No completed chores yet.</Empty>}</Panel></div></div>
}
export function Maintenance({data,mutate,show}:Props){
  function edit(issue?:Issue){
    show({title:issue?'Edit request':'Report an issue',body:<>
      <Field label="Issue" name="title" value={issue?.title}/><Notes label="Description" value={issue?.notes}/>
      <div className="form-grid"><Field label="Technician" name="technician" value={issue?.technician} required={false}/>
      <Select label="Priority" name="priority" value={issue?.priority??'MEDIUM'} options={options(['LOW','MEDIUM','HIGH','URGENT'])}/>
      <Select label="Status" name="status" value={issue?.status} options={options(['REPORTED','SCHEDULED','IN_PROGRESS','RESOLVED'])}/>
      <Field label="Estimated cost (₹)" name="estimated" type="number" min={0} step=".01" value={rupees(issue?.estimated??0)}/>
      <Field label="Actual cost (₹)" name="actual" type="number" min={0} step=".01" value={rupees(issue?.actual??0)}/></div></>,
      submit:form=>mutate(()=>api.request({url:'/maintenance/'+(issue?issue.id+'/':''),method:issue?'PATCH':'POST',data:{
        title:value(form,'title'),notes:value(form,'notes'),technician:value(form,'technician'),priority:value(form,'priority'),status:value(form,'status'),
        estimated:toPaise(value(form,'estimated')),actual:toPaise(value(form,'actual'))
      }}),'Request saved')})
  }
  return <Panel title="Maintenance requests" action={<Action onClick={()=>edit()}><Plus size={17}/> Report issue</Action>}>
    {data.issues.length?<div className="rows">{data.issues.map(i=><div className="row" key={i.id}><span className="row-icon"><Wrench size={17}/></span>
      <div className="grow"><strong>{i.title}</strong><small>{memberName(data.members,i.reported_by)} · {i.priority}{i.technician?' · '+i.technician:''}{i.resolved?' · Resolved '+i.resolved:''}</small>{i.notes&&<small>{i.notes}</small>}</div>
      <Pill tone={i.status==='RESOLVED'?'green':'amber'}>{i.status.replaceAll('_',' ')}</Pill><strong className="amount">{money(i.actual||i.estimated)}</strong>
      {i.expense?<Pill tone="green">Expense linked</Pill>:<button className="secondary" onClick={()=>show({title:'Convert to shared expense',body:<><p>Split {money(i.actual||i.estimated)} equally in the active billing cycle.</p><Select label="Paid by" name="payer" options={memberOptions(data)}/></>,label:'Create expense',submit:form=>mutate(()=>api.post('/maintenance/'+i.id+'/convert-to-expense/',{payer:number(form,'payer')}),'Expense created')})}>Convert</button>}
      <button className="icon" aria-label={'Edit '+i.title} onClick={()=>edit(i)}><Pencil size={15}/></button>
    </div>)}</div>:<Empty>No maintenance requests yet.</Empty>}
  </Panel>
}
export function Reminders({data,mutate,show}:Props){
  return <Panel title="Notifications" action={<Action onClick={()=>show({title:'Add reminder',body:<><Field label="Title" name="title"/><Notes/></>,label:'Add reminder',submit:form=>mutate(()=>api.post('/reminders/',{title:value(form,'title'),notes:value(form,'notes')}),'Reminder added')})}><Plus size={17}/> Add reminder</Action>}>
    {data.reminders.length?data.reminders.map(r=><div className="row" key={r.id}><span className="row-icon"><Bell size={17}/></span><div className="grow"><strong>{r.title}</strong><small>{r.created_at.slice(0,10)} · {r.kind.toLowerCase()}</small>{r.notes&&<small>{r.notes}</small>}</div>
      {!r.read&&<button className="secondary" onClick={()=>void mutate(()=>api.patch('/reminders/'+r.id+'/',{read:true}),'Marked as read').catch(()=>undefined)}>Mark read</button>}
      <button className="icon" aria-label={'Dismiss '+r.title} onClick={()=>void mutate(()=>api.delete('/reminders/'+r.id+'/'),'Reminder dismissed').catch(()=>undefined)}><Trash2 size={15}/></button>
    </div>):<Empty>You're all caught up.</Empty>}
  </Panel>
}
type ChartRow={name:string;total:number}
export function Reports({data,mutate,show,lead,chooseFlat,revision}:Props&{chooseFlat:(id:number)=>void;revision:number}){
  const [charts,setCharts]=useState<ChartRow[][]|null>(null)
  const [error,setError]=useState('')
  useEffect(()=>{
    const controller=new AbortController()
    Promise.all(['monthly','categories','trips','contributions'].map(k=>api.get('/reports/'+k+'/',{signal:controller.signal}))).then(res=>{
      setCharts(res.map((r,i)=>i===3?r.data.map((row:{member:number;paid:number})=>({name:memberName(data.members,row.member),total:row.paid})):r.data))
      setError('')
    }).catch(problem=>{if(!controller.signal.aborted)setError(errorText(problem))})
    return ()=>controller.abort()
  },[revision,data.members])
  async function download(){
    try{
      const {data}=await api.get('/export/')
      const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}))
      const anchor=document.createElement('a');anchor.href=url;anchor.download='broshare-backup.json';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
    }catch(problem){setError(errorText(problem))}
  }
  return <div className="stack"><FormError message={error}/>
    <div className="two-col">{charts?charts.map((rows,i)=><Panel key={i} title={['Monthly spending','By category','Trip spending','Flatmate contributions'][i]}>
      {rows.length?<div className="chart"><ResponsiveContainer width="100%" height={220}><BarChart data={rows}>
        <CartesianGrid vertical={false} stroke="#e7ebe7"/><XAxis dataKey="name" tick={{fontSize:11}} tickMargin={8}/><YAxis tick={{fontSize:11}} tickFormatter={n=>money(n)}/>
        <Tooltip formatter={v=>[money(Number(v ?? 0)),'Total']}/><Bar dataKey="total" fill="#167652" radius={[5,5,0,0]}/>
      </BarChart></ResponsiveContainer></div>:<Empty>Add expenses to populate this report.</Empty>}
      {i===0&&rows.length>1&&<p className="muted chart-note">Latest month compared with previous month · {money(rows.at(-1)!.total-rows.at(-2)!.total)}</p>}
    </Panel>):<div className="skeleton" aria-label="Loading reports"/>}</div>
    <Panel title="Settlement history"><History payments={data.payments} data={data}/></Panel>
    {lead&&<Panel title="Workspace backup"><p className="muted">Import creates a separate workspace. Member sign-ins are excluded from exports.</p><div className="actions backup-actions">
      <button className="secondary" onClick={()=>void download()}><Download size={16}/> Export JSON</button>
      <button className="secondary" onClick={()=>show({title:'Import workspace backup',body:<>
        <p>Confirm that you want to create a workspace from this backup.</p><label className="field">BroShare JSON file<input name="backup" type="file" accept=".json,application/json" required/></label>
      </>,label:'Confirm import',submit:async form=>{
        const file=form.get('backup')
        if(!(file instanceof File)||file.size>2_000_000) throw new Error('Select a JSON export smaller than 2 MB.')
        const backup=JSON.parse(await file.text())
        let flat=0
        await mutate(async()=>{const {data}=await api.post('/import/',{confirmed:true,backup});flat=data.id},'Workspace imported')
        chooseFlat(flat)
      }})}>Import JSON</button>
    </div></Panel>}
  </div>
}
export function Settings({data,show,mutate,lead,profile,member,refreshProfile}:Props&{profile:Profile;member:number;refreshProfile:()=>Promise<void>}){
  const [workspace,setWorkspace]=useState<{name:string;invite:string|null}|null>(null)
  const [error,setError]=useState('')
  const mine=data.members.find(m=>m.id===member)
  useEffect(()=>{api.get('/workspace/').then(r=>setWorkspace(r.data)).catch(e=>setError(errorText(e)))},[])
  return <div className="stack"><Panel title="Your profile" action={<button className="secondary" onClick={()=>show({title:'Edit your profile',body:<>
    <Field label="Email" name="email" type="email" required={false} value={profile.email}/><Field label="Display name" name="name" value={mine?.name}/><Field label="UPI ID" name="upi" required={false} value={mine?.upi}/>
  </>,submit:form=>mutate(async()=>{await api.patch('/roommates/'+member+'/',{name:value(form,'name'),upi:value(form,'upi')});await api.patch('/auth/me/',{email:value(form,'email')});await refreshProfile()},'Profile saved')})}><Pencil size={16}/> Edit profile</button>}>
    <div className="row"><span className="row-icon"><UserRound size={17}/></span><div><strong>{mine?.name??profile.username}</strong><small>{profile.username} · {profile.email||'No email set'}</small></div></div>
  </Panel><Panel title="Workspace"><FormError message={error}/>{workspace&&<div className="form">
    <p>{workspace.name}</p>{lead&&<><label className="field">Invite code<input readOnly value={workspace.invite??''} onFocus={e=>e.currentTarget.select()}/></label>
    <div className="actions"><button className="secondary" onClick={()=>show({title:'Rename workspace',body:<Field label="Flat name" name="name" value={workspace.name}/>,submit:form=>mutate(async()=>{const result=await api.patch('/workspace/',{name:value(form,'name')});setWorkspace(result.data);await refreshProfile()},'Workspace renamed')})}>Rename</button>
    <button className="secondary" onClick={()=>show({title:'Rotate invite code',body:<p>The current invite code will expire.</p>,label:'Rotate invite',submit:()=>mutate(async()=>{const result=await api.post('/workspace/');setWorkspace(result.data)},'Invite rotated')})}>Rotate code</button></div></>}
  </div>}</Panel></div>
}



