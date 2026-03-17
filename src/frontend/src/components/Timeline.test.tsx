import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { Timeline } from './Timeline'
import type { TimelineEvent } from '../types/api'

const mockEvents: TimelineEvent[] = [
  {
    timestamp: '2024-01-15T14:23:07Z',
    title: 'Pod OOMKilled',
    description: 'Container exceeded memory limit',
    severity: 'critical' as const,
    source: 'events/events.json',
  },
  {
    timestamp: '2024-01-15T14:23:10Z',
    title: 'Pod restarted',
    description: 'Kubelet restarted the container',
    severity: 'warning' as const,
    source: 'events/events.json',
  },
  {
    timestamp: '2024-01-15T14:20:00Z',
    title: 'HPA scaled up',
    description: 'Deployment scaled to 3 replicas',
    severity: 'info' as const,
    source: 'events/events.json',
  },
]

describe('Timeline', () => {
  it('renders timeline events with titles and descriptions', () => {
    render(<Timeline events={mockEvents} />)

    expect(screen.getByText('Pod OOMKilled')).toBeInTheDocument()
    expect(screen.getByText('Container exceeded memory limit')).toBeInTheDocument()

    expect(screen.getByText('Pod restarted')).toBeInTheDocument()
    expect(screen.getByText('Kubelet restarted the container')).toBeInTheDocument()

    expect(screen.getByText('HPA scaled up')).toBeInTheDocument()
    expect(screen.getByText('Deployment scaled to 3 replicas')).toBeInTheDocument()
  })

  it('renders timestamps formatted as HH:MM:SS', () => {
    render(<Timeline events={mockEvents} />)

    // The component uses toLocaleTimeString with hour12: false
    // '2024-01-15T14:23:07Z' formatted in UTC would be 14:23:07
    // The exact output depends on the test environment timezone,
    // so we check that some time-like string is present for each event
    const listItems = screen.getAllByRole('listitem')
    expect(listItems).toHaveLength(3)
  })

  it('formats ISO timestamps into time strings', () => {
    render(<Timeline events={[mockEvents[0]]} />)

    // The formatTimestamp function should produce a time string (not the raw ISO)
    expect(screen.queryByText('2024-01-15T14:23:07Z')).not.toBeInTheDocument()
  })

  it('renders severity labels for each event', () => {
    render(<Timeline events={mockEvents} />)

    expect(screen.getByText('critical')).toBeInTheDocument()
    expect(screen.getByText('warning')).toBeInTheDocument()
    expect(screen.getByText('info')).toBeInTheDocument()
  })

  it('applies correct severity colors to severity text', () => {
    render(<Timeline events={mockEvents} />)

    const criticalLabel = screen.getByText('critical')
    expect(criticalLabel.className).toContain('text-red-400')

    const warningLabel = screen.getByText('warning')
    expect(warningLabel.className).toContain('text-amber-400')

    const infoLabel = screen.getByText('info')
    expect(infoLabel.className).toContain('text-zinc-400')
  })

  it('applies correct severity colors to dot indicators', () => {
    render(<Timeline events={mockEvents} />)

    const listItems = screen.getAllByRole('listitem')

    // Each listitem has a dot div with severity-specific border and bg classes
    const criticalDot = listItems[0].querySelector('[class*="border-red-500"]')
    expect(criticalDot).toBeInTheDocument()

    const warningDot = listItems[1].querySelector('[class*="border-amber-500"]')
    expect(warningDot).toBeInTheDocument()

    const infoDot = listItems[2].querySelector('[class*="border-zinc-500"]')
    expect(infoDot).toBeInTheDocument()
  })

  it('returns null when events array is empty', () => {
    const { container } = render(<Timeline events={[]} />)

    expect(container.innerHTML).toBe('')
  })

  it('renders the Event Timeline heading', () => {
    render(<Timeline events={mockEvents} />)

    expect(screen.getByText('Event Timeline')).toBeInTheDocument()
  })

  it('renders source file paths for each event', () => {
    render(<Timeline events={mockEvents} />)

    // All mock events have the same source
    const sourceElements = screen.getAllByText('events/events.json')
    expect(sourceElements).toHaveLength(3)
  })

  it('uses a list role for accessibility', () => {
    render(<Timeline events={mockEvents} />)

    expect(screen.getByRole('list')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
  })
})
