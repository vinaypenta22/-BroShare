import {useCallback,useEffect,useRef,useState,type FormEvent,type ReactNode} from 'react'
import {Navigate,NavLink,useLocation,useNavigate} from 'react-router-dom'
import {ArrowLeftRight,BarChart3,Bell,CalendarDays,ChevronDown,House,LayoutGrid,LogOut,Plane,Plus,Receipt,Users,WalletCards,X} from 'lucide-react'
import {api,errorText,list,signIn,signOut,useSession,type Profile} from './api'
import {BalanceRows,BillingDialog,ExpenseDialog,ExpenseRows,Filters,History,PaymentDialog,SettlementRows,SummaryCard,type Mutate,type Scope} from './finance'
import {FormDialog,Members,Reminders,Reports,Trips,type Modal} from './modules'
import {Action,Empty,Field,FormError,Panel,Pill,value} from './ui'
import {money,today,type Data,type Expense,type Payment,type Summary,type Transfer} from './types'

const navigation=[
  ['Dashboard','/',LayoutGrid],
  ['Expenses','/expenses',Receipt],['Settlements','/settlements',ArrowLeftRight],
  ['Flatmates','/flatmates',Users],['Group trips','/trips',Plane],
  ['Reports','/reports',BarChart3],
] as const

function Brand(){return <div className="brand"><span><WalletCards size={22}/></span><strong>BroShare</strong></div>}

function SignIn(){
  const [register,setRegister]=useState(false)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  async function submit(event:FormEvent<HTMLFormElement>){
    event.preventDefault();setBusy(true);setError('')
    const form=new FormData(event.currentTarget)
    try{await signIn(value(form,'username'),value(form,'password'),register)}
    catch(problem){setError(errorText(problem))}
    finally{setBusy(false)}
  }
  return <main className="auth">
    <section className="auth-brand"><Brand/><div><span className="auth-mark"><House size={42}/></span><h1>Shared living.<br/>Clear balances.</h1><p>Keep bills, trip costs and household responsibilities in one place.</p></div></section>
    <section className="auth-main"><form className="form auth-form" onSubmit={submit}><Brand/>
      <div><h2>{register?'Create your account':'Welcome back'}</h2><p className="muted">{register?'Create a flat or join with an invite code.':'Sign in to your shared workspace.'}</p></div>
      <label className="field">Username<input name="username" autoComplete="username" required/></label>
      <label className="field">Password<input type="password" name="password" autoComplete={register?'new-password':'current-password'} required/></label>
      <FormError message={error}/><button className="primary" disabled={busy}>{busy?'Please wait…':register?'Create account':'Sign in'}</button>
      <p>{register?'Already have an account?':'New to BroShare?'} <button type="button" className="text-button" onClick={()=>{setRegister(!register);setError('')}}>{register?'Sign in':'Sign up'}</button></p>
    </form></section>
  </main>
}

export function App(){
  const authenticated=useSession(state=>Boolean(state.tokens))
  return authenticated?<Account/>:<SignIn/>
}
function Account(){
  const [profile,setProfile]=useState<Profile|null>(null)
  const [error,setError]=useState('')
  const [modal,setModal]=useState<Modal|null>(null)
  const flat=useSession(s=>s.flat)
  const choose=useSession(s=>s.choose)
  const refreshProfile=useCallback(async()=>{const {data}=await api.get<Profile>('/auth/me/');setProfile(data)},[])
  useEffect(()=>{void refreshProfile().catch(problem=>setError(errorText(problem)))},[refreshProfile])
  const active=profile?.flats.find(x=>x.id===flat)??profile?.flats[0]
  useEffect(()=>{if(active&&active.id!==flat)choose(active.id)},[active,flat,choose])
  async function chooseFlat(id:number){await refreshProfile();choose(id)}
  function openFlat(join:boolean){
    setModal({title:join?'Join a flat':'Create a flat',body:<><Field label={join?'Your display name':'Flat name'} name="name"/>{join&&<Field label="Invite code" name="invite"/>}</>,label:join?'Join flat':'Create flat',
      submit:async form=>{const {data}=await api.post('/flats/',{name:value(form,'name'),invite:value(form,'invite')});await chooseFlat(data.id)}})
  }
  const quit=()=>void signOut().catch(()=>undefined)
  return <>{modal&&<FormDialog modal={modal} close={()=>setModal(null)}/>}
    {profile&&active&&active.id===flat?<Workspace key={flat} profile={profile} active={active} chooseFlat={id=>void chooseFlat(id).catch(e=>setError(errorText(e)))} openFlat={openFlat} quit={quit}/>:
      <main className="onboard"><Brand/><FormError message={error}/>
        {error&&<button className="secondary" onClick={()=>void refreshProfile().then(()=>setError('')).catch(e=>setError(errorText(e)))}>Retry</button>}
        {profile&&!active?<Panel title="Set up your flat"><p className="muted">Start a workspace or use an invite from your flat lead.</p><div className="actions backup-actions"><Action onClick={()=>openFlat(false)}>Create flat</Action><button className="secondary" onClick={()=>openFlat(true)}>Join flat</button><button className="secondary" onClick={quit}>Sign out</button></div></Panel>:!error&&<div className="skeleton" aria-label="Loading workspace"/>}
        {error&&<button className="text-button" onClick={quit}>Sign out</button>}
      </main>}
  </>
}

function Workspace({profile,active,chooseFlat,openFlat,quit}:{
  profile:Profile;active:Profile['flats'][number];chooseFlat:(id:number)=>void;openFlat:(join:boolean)=>void;quit:()=>void
}){
  const {pathname}=useLocation()
  const navigate=useNavigate()
  const [data,setData]=useState<Data|null>(null)
  const [summary,setSummary]=useState<Summary|null>(null)
  const [revision,setRevision]=useState(0)
  const [cycleID,setCycle]=useState<number|'all'|null>(null)
  const [tripID,setTrip]=useState<number|null>(null)
  const [modal,setModal]=useState<ReactNode>(null)
  const [notice,setNotice]=useState('')
  const [error,setError]=useState('')
  const [summaryError,setSummaryError]=useState('')
  const loadRef=useRef<AbortController|null>(null)
  const version=useRef('')
  const mounted=useRef(false)
  const lead=active.role==='LEAD'
  const refresh=useCallback(async()=>{
    loadRef.current?.abort()
    const controller=new AbortController()
    loadRef.current=controller
    const {signal}=controller
    try{
      const marker=await api.get('/sync-check/',{signal})
      const [members,cycles,trips,expenses,payments,chores,issues,reminders]=await Promise.all([
        list<Data['members'][number]>('/roommates/',signal),list<Data['cycles'][number]>('/billing-cycle/',signal),
        list<Data['trips'][number]>('/trips/',signal),list<Data['expenses'][number]>('/expenses/',signal),
        list<Data['payments'][number]>('/settlements/',signal),list<Data['chores'][number]>('/chores/',signal),
        list<Data['issues'][number]>('/maintenance/',signal),list<Data['reminders'][number]>('/reminders/',signal)
      ])
      if(signal.aborted)return
      setData({members,cycles,trips,expenses,payments,chores,issues,reminders})
      version.current=marker.data.updated_at
      setRevision(v=>v+1)
      setError('')
    }catch(problem){if(!signal.aborted)setError(errorText(problem))}
  },[])
  useEffect(()=>{
    mounted.current=true
    void refresh()
    let checking=false
    async function check(){
      if(checking||loadRef.current&&!version.current) return
      checking=true
      try{const {data}=await api.get('/sync-check/');if(mounted.current&&data.updated_at!==version.current) await refresh()}
      catch(problem){if(mounted.current)setError(errorText(problem))}
      finally{checking=false}
    }
    const timer=setInterval(()=>void check(),5000)
    return ()=>{mounted.current=false;loadRef.current?.abort();clearInterval(timer)}
  },[refresh])
  useEffect(()=>{if(!notice)return;const timer=setTimeout(()=>setNotice(''),3600);return ()=>clearTimeout(timer)},[notice])
  const cycle=data?.cycles.find(c=>c.id===cycleID)??data?.cycles[0]
  const trip=pathname==='/trips'?(data?.trips.find(t=>t.id===tripID)??data?.trips[0]):undefined
  const scope:Scope=pathname==='/trips'?{trip}:{cycle,all:cycleID==='all'}
  const scopeKey=trip?'trip='+trip.id:scope.all?'cycle=all':cycle?'cycle='+cycle.id:''
  const needsSummary=['/','/trips','/settlements'].includes(pathname) && (pathname!=='/trips'||Boolean(trip))
  useEffect(()=>{
    setSummary(null);setSummaryError('')
    if(!needsSummary||!scopeKey)return
    const controller=new AbortController()
    api.get<Summary>('/summary/?'+scopeKey,{signal:controller.signal}).then(response=>setSummary(response.data))
      .catch(problem=>{if(!controller.signal.aborted)setSummaryError(errorText(problem))})
    return ()=>controller.abort()
  },[scopeKey,needsSummary,revision])
  const mutate:Mutate=async(operation,message)=>{
    try{await operation();if(message)setNotice(message);await refresh()}
    catch(problem){setNotice(errorText(problem));throw problem}
  }
  const close=()=>setModal(null)
  const show=(config:Modal)=>setModal(<FormDialog modal={config} close={close}/>)
  const newExpense=(item?:Expense)=>{if(data)setModal(<ExpenseDialog data={data} scope={scope.all||scope.cycle?.status!=='ACTIVE'?{trip:scope.trip}:scope} item={item} close={close} mutate={mutate}/>)}
  const removeExpense=(item:Expense)=>show({title:'Delete '+item.title,body:<p>This expense will be removed from the balances and reports.</p>,label:'Delete expense',submit:()=>mutate(()=>api.delete('/expenses/'+item.id+'/'),'Expense deleted')})
  const pay=(payment:Transfer,pending?:Payment)=>{if(data)setModal(<PaymentDialog data={data} scope={scope} transfer={payment} pending={pending} close={close} mutate={mutate}/>)}
  const reverse=(item:Payment)=>show({title:'Reverse settlement',body:<p>Reverse {money(item.paise)} and recalculate the outstanding balance. The payment stays in history.</p>,label:'Reverse payment',submit:()=>mutate(()=>api.post('/settlements/'+item.id+'/reverse/'),'Payment reversed')})
  function addCycle(){
    show({title:'Open billing month',body:<Field label="Billing month" name="month" type="month" value={today().slice(0,7)}/>,label:'Open month',submit:async form=>{
      let id=0;await mutate(async()=>{const {data}=await api.post('/billing-cycle/',{month:value(form,'month')});id=data.id},'Billing month opened');setCycle(id)
    }})
  }
  const name=profile.username
  const title=pathname==='/notifications'?'Notifications':navigation.find(([,path])=>pathname===path)?.[0]??'Dashboard'
  const unread=data?.reminders.filter(r=>!r.read).length??0
  function content(){
    if(!data)return <div className="skeleton" aria-label="Loading dashboard"/>
    const props={data,mutate,show,lead}
    const financial=summary
    const expenses=data.expenses.filter(e=>trip?e.trip===trip.id:!e.trip&&(scope.all||e.cycle===cycle?.id))
    const payments=data.payments.filter(p=>trip?p.trip===trip.id:!p.trip&&(scope.all||p.cycle===cycle?.id))
    const editable=(e:Expense)=>e.trip?data.trips.some(t=>t.id===e.trip):data.cycles.some(c=>c.id===e.cycle&&c.status==='ACTIVE')
    const editExpense=(e:Expense)=>editable(e)?newExpense(e):setNotice('Reopen the billing cycle or choose an active trip to edit this expense.')
    const deleteExpense=(e:Expense)=>editable(e)?removeExpense(e):setNotice('Reopen the billing cycle or choose an active trip to delete this expense.')
    if(pathname==='/expenses')return <Filters data={data} rows={data.expenses} onAdd={()=>newExpense()} onEdit={editExpense} onDelete={deleteExpense}/>
    if(pathname==='/flatmates')return <div className="stack"><Members {...props}/><Panel title="Workspace">
      <div className="workspace-switch"><House size={17}/><label className="workspace-select"><span className="sr-only">Workspace</span><select value={active.id} onChange={e=>e.target.value==='create'?openFlat(false):e.target.value==='join'?openFlat(true):chooseFlat(Number(e.target.value))}>
        {profile.flats.map(f=><option value={f.id} key={f.id}>{f.name}</option>)}<option value="create">Create a flat</option><option value="join">Join a flat</option></select></label><ChevronDown size={14}/></div>
</Panel></div>
    if(pathname==='/reports')return <Reports {...props} chooseFlat={chooseFlat} revision={revision}/>
    if(pathname==='/notifications')return <Reminders {...props}/>
    const billing=<section className="month-toolbar" aria-label="Billing period">
      <label className="month-picker"><span className="month-icon"><CalendarDays size={19}/></span>
        <span className="month-field"><span>Billing month</span><select value={scope.all?'all':cycle?.id??''} onChange={event=>setCycle(event.target.value==='all'?'all':Number(event.target.value))}>
          {!data.cycles.length&&<option value="" disabled>No billing months</option>}
          {data.cycles.map(c=><option value={c.id} key={c.id}>{new Intl.DateTimeFormat('en-IN',{month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(c.month+'-01T00:00:00Z'))}</option>)}
          <option value="all">All months</option>
        </select></span>
      </label>
      <div className="actions">{cycle&&!scope.all&&<Pill tone={cycle.status==='SETTLED'?'green':cycle.status==='CLOSED'?'amber':'neutral'}>
        {cycle.status==='SETTLED'?'Settled':cycle.status==='CLOSED'?'Closed':'Open'}
      </Pill>}{lead&&<button className="secondary" onClick={addCycle}><Plus size={16}/> Open month</button>}</div>
    </section>
    const history=<Panel title="Settlement history"><History payments={payments} data={data} confirm={item=>pay(item,item)} reverse={item=>{
      if(lead||item.payer===active.member)reverse(item);else setNotice('Only the payer or flat lead can reverse this settlement.')
    }}/></Panel>
    const totals=financial?<SummaryCard summary={financial} member={active.member} trip={trip}/>:null
    const transfers=financial?<Panel title="Suggested transfers" action={financial.pending>0&&<Pill tone="amber">{money(financial.pending)} pending</Pill>}><SettlementRows data={data} summary={financial} canPay={!scope.all} onPay={payment=>{
      const pending=payments.find(p=>p.status==='PENDING'&&p.payer===payment.payer&&p.receiver===payment.receiver&&p.paise===payment.paise)
      pay(payment,pending)
    }}/></Panel>:null
    const recent=<Panel title="Recent expenses" action={trip&&<button className="secondary" onClick={()=>newExpense()}><Plus size={16}/> Add expense</button>}>
      <ExpenseRows rows={expenses.slice(0,8)} data={data} edit={editExpense} remove={deleteExpense}/></Panel>
    const balance=financial&&<Panel title={trip?'Traveller balances':'Flatmate balances'}><BalanceRows data={data} summary={financial}/></Panel>
    const state=summaryError?<FormError message={summaryError}/>:needsSummary&&!financial?<div className="skeleton" aria-label="Loading balances"/>:null
    if(pathname==='/trips')return <div className="stack"><Trips {...props} active={trip} choose={setTrip}/>
      {trip&&<><div className="section-head"><h2>{trip.name}</h2><span className="muted">Budget {money(trip.budget)}</span></div>{state}{totals}<div className="two-col">{transfers}{balance}</div>{recent}{history}</>}
    </div>
    if(pathname==='/settlements') return <div className="stack">{billing}{state}{transfers}{history}</div>
    return <div className="stack">
      {billing}{state}{totals}
      {cycle&&!scope.all&&lead&&financial&&<div className="actions">
        {cycle.status==='ACTIVE'?<button className="secondary" onClick={()=>setModal(<BillingDialog cycle={cycle} summary={financial} data={data} close={close} mutate={mutate} choose={setCycle}/>)}>Settle up &amp; open next month</button>:
        <button className="secondary" onClick={()=>show({title:'Reopen '+cycle.month,body:<p>Reopening allows edits and keeps all settlement records.</p>,label:'Reopen cycle',submit:()=>mutate(()=>api.post('/billing-cycle/reopen/',{cycle:cycle.id}),'Cycle reopened')})}>Reopen cycle</button>}
      </div>}
      <div className="dashboard-grid">{recent}<div className="stack">{balance}{transfers}</div></div>
      {!cycle&&<Empty>Open a billing cycle to start recording household expenses.</Empty>}
    </div>
  }
  if(['/maintenance','/chores','/settings'].includes(pathname))return <Navigate to="/" replace/>
  return <div className="dashboard-shell">
    <header className="dashboard-header"><div className="dashboard-header-inner">
      <NavLink to="/" aria-label="BroShare dashboard"><Brand/></NavLink>
      <nav className="header-tabs" aria-label="Main navigation">
        {navigation.map(([label,path,Icon])=><NavLink to={path} key={path} end><Icon size={16}/>{label}</NavLink>)}
      </nav>
      <div className="header-actions"><button className="icon bell" aria-label={unread+' unread notifications'} onClick={()=>navigate('/notifications')}><Bell size={20}/>{unread>0&&<i/>}</button>
        <button className="icon" title="Sign out" aria-label={'Sign out '+name} onClick={quit}><LogOut size={18}/></button></div>
    </div></header>
    <main className="content dashboard-content">
      <div className="page-head"><div>
        <h1>{title}</h1><p className="muted">{pathname==='/'?'See what your flat spent and who owes what.':active.name}</p></div>
        {pathname==='/'&&data?.cycles.some(c=>c.status==='ACTIVE')&&<Action onClick={()=>newExpense()}><Plus size={17}/> Add expense</Action>}</div>
      {error&&<div className="actions"><FormError message={error}/><button className="secondary" onClick={()=>void refresh()}>Retry</button></div>}{content()}
    </main>{modal}{notice&&<div className="toast" role="status">{notice}<button aria-label="Dismiss message" onClick={()=>setNotice('')}><X size={17}/></button></div>}
  </div>
}





