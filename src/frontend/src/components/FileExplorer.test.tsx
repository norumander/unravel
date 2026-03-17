import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import FileExplorer from './FileExplorer'
import type { BundleManifest } from '../types/api'

const mockManifest: BundleManifest = {
  total_files: 4,
  total_size_bytes: 10240,
  files: [
    { path: 'events/events.json', size_bytes: 5120, signal_type: 'events' },
    { path: 'events/ns1/events.json', size_bytes: 1024, signal_type: 'events' },
    { path: 'pod-logs/app.log', size_bytes: 3072, signal_type: 'pod_logs' },
    { path: 'cluster-info/nodes.json', size_bytes: 1024, signal_type: 'cluster_info' },
  ],
}

const emptyManifest: BundleManifest = {
  total_files: 0,
  total_size_bytes: 0,
  files: [],
}

describe('FileExplorer', () => {
  const mockOnFileSelect = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders signal type groups from manifest data', () => {
    render(<FileExplorer manifest={mockManifest} onFileSelect={mockOnFileSelect} />)

    expect(screen.getByText('Events')).toBeInTheDocument()
    expect(screen.getByText('Pod Logs')).toBeInTheDocument()
    expect(screen.getByText('Cluster Info')).toBeInTheDocument()
  })

  it('shows file count and total size per group', () => {
    render(<FileExplorer manifest={mockManifest} onFileSelect={mockOnFileSelect} />)

    // Events group: 2 files, 6144 bytes = 6.0 KB
    expect(screen.getByText(/2 files/)).toBeInTheDocument()
    // Pod Logs and Cluster Info each have 1 file
    const singleFileLabels = screen.getAllByText(/1 file ·/)
    expect(singleFileLabels).toHaveLength(2)
  })

  it('events group is expanded by default and others are collapsed', () => {
    render(<FileExplorer manifest={mockManifest} onFileSelect={mockOnFileSelect} />)

    // Events group is expanded by default, so its files should be visible
    expect(screen.getByText('events/events.json')).toBeInTheDocument()
    expect(screen.getByText('ns1/events.json')).toBeInTheDocument()

    // Pod Logs group is collapsed, so its file should not be visible
    expect(screen.queryByText('pod-logs/app.log')).not.toBeInTheDocument()
    // Cluster Info is collapsed too
    expect(screen.queryByText('cluster-info/nodes.json')).not.toBeInTheDocument()
  })

  it('clicking a group header toggles file list visibility', () => {
    render(<FileExplorer manifest={mockManifest} onFileSelect={mockOnFileSelect} />)

    // Events is expanded by default — collapse it
    fireEvent.click(screen.getByText('Events'))
    expect(screen.queryByText('events/events.json')).not.toBeInTheDocument()

    // Click again to expand
    fireEvent.click(screen.getByText('Events'))
    expect(screen.getByText('events/events.json')).toBeInTheDocument()
  })

  it('clicking a collapsed group expands it to show files', () => {
    render(<FileExplorer manifest={mockManifest} onFileSelect={mockOnFileSelect} />)

    // Pod Logs is collapsed — expand it
    fireEvent.click(screen.getByText('Pod Logs'))
    expect(screen.getByText('pod-logs/app.log')).toBeInTheDocument()
  })

  it('displays files with truncated paths', () => {
    render(<FileExplorer manifest={mockManifest} onFileSelect={mockOnFileSelect} />)

    // 'events/ns1/events.json' has 3 segments, so truncated to last 2: 'ns1/events.json'
    expect(screen.getByText('ns1/events.json')).toBeInTheDocument()
    // 'events/events.json' has 2 segments, not truncated
    expect(screen.getByText('events/events.json')).toBeInTheDocument()
  })

  it('displays file sizes', () => {
    render(<FileExplorer manifest={mockManifest} onFileSelect={mockOnFileSelect} />)

    // 5120 bytes = 5.0 KB
    expect(screen.getByText('5.0 KB')).toBeInTheDocument()
    // 1024 bytes = 1.0 KB
    expect(screen.getByText('1.0 KB')).toBeInTheDocument()
  })

  it('clicking a file calls onFileSelect with the file path', () => {
    render(<FileExplorer manifest={mockManifest} onFileSelect={mockOnFileSelect} />)

    // Events group is expanded by default
    fireEvent.click(screen.getByText('events/events.json'))
    expect(mockOnFileSelect).toHaveBeenCalledWith('events/events.json')
  })

  it('empty manifest shows no groups', () => {
    const { container } = render(
      <FileExplorer manifest={emptyManifest} onFileSelect={mockOnFileSelect} />,
    )

    expect(screen.queryByText('Events')).not.toBeInTheDocument()
    expect(screen.queryByText('Pod Logs')).not.toBeInTheDocument()
    expect(screen.queryByText('Cluster Info')).not.toBeInTheDocument()
    // The container should have no group buttons
    expect(container.querySelectorAll('button')).toHaveLength(0)
  })
})
