import { useEffect, useState, type ChangeEvent, type DragEvent } from 'react'
import { motion } from 'framer-motion'
import { Link } from 'react-router-dom'
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  CloudSun,
  Heart,
  ImagePlus,
  Leaf,
  ScanLine,
  Sprout,
  Trash2,
  UploadCloud,
  type LucideIcon,
} from 'lucide-react'

type MetricCardProps = {
  label: string
  description: string
  icon: LucideIcon
  tone: 'green' | 'mint' | 'rose' | 'gold'
  to: string
  index: number
}

const metricCards: Omit<MetricCardProps, 'index'>[] = [
  {
    label: 'Total Scans',
    description: 'Live records will appear here',
    icon: ScanLine,
    tone: 'green',
    to: '/history',
  },
  {
    label: 'Healthy Crops',
    description: 'Based on saved scan results',
    icon: Heart,
    tone: 'mint',
    to: '/results',
  },
  {
    label: 'Diseases Detected',
    description: 'From actual model predictions',
    icon: AlertTriangle,
    tone: 'rose',
    to: '/results',
  },
  {
    label: 'Crops Monitored',
    description: 'Your connected crop records',
    icon: Sprout,
    tone: 'gold',
    to: '/diseases',
  },
]

function greetingForTime() {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}

function MetricCard({ label, description, icon: Icon, tone, to, index }: MetricCardProps) {
  return (
    <motion.div
      animate={{ opacity: 1, y: 0 }}
      className={`metric-card metric-${tone}`}
      initial={{ opacity: 0, y: 12 }}
      transition={{ delay: index * 0.06, duration: 0.32 }}
      whileHover={{ y: -3, transition: { duration: 0.16 } }}
    >
      <Link aria-label={`${label}. ${description}`} className="metric-card-link" to={to}>
        <span className="metric-icon"><Icon aria-hidden="true" size={21} strokeWidth={2} /></span>
        <span className="metric-copy"><span>{label}</span><strong aria-label="No data yet">—</strong><small>{description}</small></span>
        <ArrowUpRight aria-hidden="true" className="metric-arrow" size={16} />
      </Link>
    </motion.div>
  )
}

function CropHealthChart() {
  const [range, setRange] = useState('7')
  return (
    <section aria-labelledby="health-analytics-heading" className="panel analytics-panel">
      <div className="panel-heading">
        <div className="panel-title">
          <span className="panel-heading-icon"><Activity aria-hidden="true" size={18} /></span>
          <div><h2 id="health-analytics-heading">Crop Health Analytics</h2><p>Weekly crop health trends</p></div>
        </div>
        <label className="range-select-label">
          <span className="sr-only">Chart date range</span>
          <select aria-label="Chart date range" onChange={(event) => setRange(event.target.value)} value={range}>
            <option value="7">Last 7 days</option>
            <option value="30">Last 30 days</option>
            <option value="90">Last 90 days</option>
          </select>
        </label>
      </div>
      <div className="line-chart-wrap">
        <div aria-label="Crop health chart, no saved scan data" className="line-chart-grid" role="img" />
        <div className="chart-empty-overlay">
          <span className="chart-empty-icon"><Activity aria-hidden="true" size={18} /></span>
          <strong>No scan data yet</strong>
          <span>Trends will appear after real scan results are saved.</span>
          <small>Showing the last {range} days</small>
        </div>
      </div>
      <div aria-label="Crop health chart legend" className="chart-legend">
        <span><i className="legend-healthy" />Healthy</span>
        <span><i className="legend-risk" />At risk</span>
        <span><i className="legend-diseased" />Diseased</span>
      </div>
    </section>
  )
}

function CropHealthOverview() {
  return (
    <section aria-labelledby="health-overview-heading" className="panel overview-panel">
      <div className="panel-heading">
        <div className="panel-title">
          <span className="panel-heading-icon"><Sprout aria-hidden="true" size={18} /></span>
          <div><h2 id="health-overview-heading">Crop Health Overview</h2><p>Classification from your scans</p></div>
        </div>
      </div>
      <div aria-label="No crop health data is available yet" className="donut-area">
        <div className="donut-chart">
          <div className="donut-center"><strong>—</strong><span>No data</span></div>
        </div>
        <div className="health-legend">
          <div><i className="legend-healthy" /><span>Healthy</span><strong>—</strong></div>
          <div><i className="legend-risk" /><span>At risk</span><strong>—</strong></div>
          <div><i className="legend-diseased" /><span>Critical</span><strong>—</strong></div>
        </div>
      </div>
      <div className="overview-empty-note"><Activity aria-hidden="true" size={14} /> Health distribution will use saved model results.</div>
    </section>
  )
}

function RecentDetections() {
  return (
    <section aria-labelledby="recent-detections-heading" className="panel recent-panel">
      <div className="panel-heading">
        <div className="panel-title">
          <span className="panel-heading-icon"><Activity aria-hidden="true" size={18} /></span>
          <div><h2 id="recent-detections-heading">Recent AI Detections</h2><p>Latest results saved to your account</p></div>
        </div>
        <Link className="view-all-link" to="/history">View all <ArrowUpRight aria-hidden="true" size={15} /></Link>
      </div>
      <div className="table-scroll">
        <table className="detection-table">
          <thead><tr><th scope="col">Image</th><th scope="col">Crop</th><th scope="col">Status</th><th scope="col">Confidence</th><th scope="col">Date</th></tr></thead>
          <tbody><tr><td className="table-empty-cell" colSpan={5}>
            <span className="table-empty-icon"><Leaf aria-hidden="true" size={20} /></span>
            <strong>No detections yet</strong>
            <span>Your real scan results will show here.</span>
          </td></tr></tbody>
        </table>
      </div>
    </section>
  )
}

function QuickScanCard() {
  const [preview, setPreview] = useState<{ file: File; url: string } | null>(null)
  const [error, setError] = useState('')
  const file = preview?.file ?? null

  useEffect(() => {
    return () => {
      if (preview?.url) URL.revokeObjectURL(preview.url)
    }
  }, [preview])

  function acceptFile(candidate?: File) {
    setError('')
    if (!candidate) return
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(candidate.type)) {
      setError('Choose an image file to preview.')
      return
    }
    if (candidate.size > 10 * 1024 * 1024) {
      setError('The image must be smaller than 10 MB.')
      return
    }
    setPreview({ file: candidate, url: URL.createObjectURL(candidate) })
  }

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    acceptFile(event.target.files?.[0])
    event.target.value = ''
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    acceptFile(event.dataTransfer.files[0])
  }

  return (
    <section aria-labelledby="quick-scan-heading" className="panel quick-scan-panel">
      <div className="panel-heading">
        <div className="panel-title">
          <span className="quick-scan-icon"><ScanLine aria-hidden="true" size={20} /></span>
          <div><h2 id="quick-scan-heading">Quick Scan</h2><p>Preview a crop image for detection</p></div>
        </div>
      </div>
      <input
        accept="image/jpeg,image/png,image/webp"
        className="file-input-hidden"
        id="quick-scan-file"
        onChange={handleChange}
        type="file"
      />
      <div
        aria-label="Drop a crop image here, or choose an image file"
        className={`upload-dropzone${file ? ' upload-dropzone-selected' : ''}`}
        onDragOver={(event) => event.preventDefault()}
        onDrop={handleDrop}
      >
        {preview ? (
          <div className="upload-preview">
            <img alt={`Preview of ${preview.file.name}`} src={preview.url} />
            <button aria-label="Remove selected image" className="remove-image-button" onClick={() => setPreview(null)} type="button"><Trash2 size={16} /></button>
            <span className="preview-file-name">{preview.file.name}</span>
          </div>
        ) : (
          <>
            <span className="upload-icon"><UploadCloud aria-hidden="true" size={27} /></span>
            <strong>Drag &amp; drop an image here</strong>
            <span>or choose a JPG, PNG, or WebP image</span>
          </>
        )}
      </div>
      {error && <p className="upload-error" role="alert">{error}</p>}
      <label className="button button-primary choose-image-button" htmlFor="quick-scan-file">
        <ImagePlus aria-hidden="true" size={17} />
        {file ? 'Replace image' : 'Choose image'}
      </label>
      <div className="scan-readiness">
        <CheckCircle2 aria-hidden="true" size={15} />
        <span>Image preview is ready. Detection runs only after the model service is connected.</span>
      </div>
    </section>
  )
}

export function Dashboard() {
  return (
    <div className="dashboard-page">
      <div className="dashboard-welcome-row">
        <div className="dashboard-welcome">
          <span className="eyebrow">FARM OVERVIEW</span>
          <h1>{greetingForTime()}, Farmer <Sprout aria-hidden="true" className="welcome-sprout" size={31} /></h1>
          <p>Here’s what’s happening on your farm today.</p>
        </div>
        <div className="farm-status-banner">
          <span className="status-check"><CheckCircle2 aria-hidden="true" size={20} /></span>
          <span><strong>Your farm workspace is ready</strong><small>Connect your farm data to see live insights.</small></span>
          <div aria-hidden="true" className="banner-landscape"><CloudSun size={24} /><span className="field-line field-line-one" /><span className="field-line field-line-two" /><span className="field-line field-line-three" /></div>
        </div>
      </div>

      <div className="metric-grid">
        {metricCards.map((card, index) => <MetricCard index={index} key={card.label} {...card} />)}
      </div>

      <div className="dashboard-analytics-grid">
        <CropHealthChart />
        <CropHealthOverview />
      </div>

      <div className="dashboard-bottom-grid">
        <RecentDetections />
        <QuickScanCard />
      </div>
      <p className="model-note"><CloudSun aria-hidden="true" size={14} /> Live metrics will appear after Supabase is configured. Crop detection uses the existing model; no sample predictions are shown.</p>
    </div>
  )
}
