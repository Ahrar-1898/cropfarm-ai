import {
  BarChart3,
  Bug,
  CloudSun,
  FileText,
  History,
  Home,
  MessageSquareText,
  ScanLine,
  Settings,
  type LucideIcon,
} from 'lucide-react'

export type AppNavItem = {
  label: string
  to: string
  icon: LucideIcon
  description: string
}

export const appNavigation: AppNavItem[] = [
  {
    label: 'Overview',
    to: '/',
    icon: Home,
    description: 'Farm health summary and recent activity',
  },
  {
    label: 'Crop Scanner',
    to: '/scanner',
    icon: ScanLine,
    description: 'Upload a leaf image for model analysis',
  },
  {
    label: 'Detection Results',
    to: '/results',
    icon: BarChart3,
    description: 'Review crop disease results',
  },
  {
    label: 'AI Assistant',
    to: '/assistant',
    icon: MessageSquareText,
    description: 'Ask practical agriculture questions',
  },
  {
    label: 'Crop Diseases',
    to: '/diseases',
    icon: Bug,
    description: 'Search crop disease information',
  },
  {
    label: 'Weather',
    to: '/weather',
    icon: CloudSun,
    description: 'Local weather and forecast',
  },
  {
    label: 'Detection History',
    to: '/history',
    icon: History,
    description: 'Your saved crop scans',
  },
  {
    label: 'Reports',
    to: '/reports',
    icon: FileText,
    description: 'Download crop health reports',
  },
  {
    label: 'Settings',
    to: '/settings',
    icon: Settings,
    description: 'Profile, preferences, and security',
  },
]

export function getPageLabel(pathname: string) {
  return appNavigation.find((item) => item.to === pathname)?.label ?? 'Workspace'
}
