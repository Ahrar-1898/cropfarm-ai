import { ArrowLeft, Leaf } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { appNavigation } from '../navigation'

const moduleNotes: Record<string, string> = {
  '/scanner': 'The current Python model will be connected in the detection phase. This preview will not generate predictions.',
  '/results': 'Detection statistics will come from saved model outputs, not sample dashboard values.',
  '/assistant': 'The assistant will use the Groq API from the backend after its key is configured.',
  '/diseases': 'The searchable disease library will use verified crop and disease information.',
  '/weather': 'Live weather will be displayed only after the selected provider is connected.',
  '/history': 'Your scans will appear here after authentication and database setup.',
  '/reports': 'Reports will be generated from your own saved detection records.',
  '/settings': 'Account and preference settings will be connected with Supabase Auth.',
  '/login': 'Email OTP, password login, and Google sign-in will be connected through Supabase Auth.',
  '/signup': 'Account creation and verification will be connected through Supabase Auth.',
}

export function ModulePlaceholder() {
  const { pathname } = useLocation()
  const item = appNavigation.find((navigationItem) => navigationItem.to === pathname)
  const title = item?.label ?? (pathname === '/login' ? 'Sign in' : pathname === '/signup' ? 'Create account' : 'Page not found')
  const Icon = item?.icon ?? Leaf
  const message = moduleNotes[pathname] ?? 'This page is not part of the current dashboard preview.'

  return (
    <section className="module-placeholder">
      <div className="module-placeholder-card">
        <span className="module-placeholder-icon"><Icon aria-hidden="true" size={25} /></span>
        <span className="eyebrow">CROPFARMAI WORKSPACE</span>
        <h1>{title}</h1>
        <p>{message}</p>
        <Link className="button button-primary" to="/"><ArrowLeft aria-hidden="true" size={16} /> Back to overview</Link>
      </div>
    </section>
  )
}
