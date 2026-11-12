import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test, vi } from 'vitest'
import InlineDraftField from './InlineDraftField'

function setup(list = false) {
  const onApply = vi.fn()
  const onPendingChange = vi.fn()
  const onSelect = vi.fn()
  render(<><InlineDraftField path={list ? 'needs/0' : 'name'} label="Value" value="Original" displayValue="Original"
    onApply={onApply} onPendingChange={onPendingChange} onSelect={onSelect} /><button>Next</button></>)
  return { onApply, onPendingChange, onSelect }
}

test('click opens the raw value; Enter applies, Escape cancels, both restore focus', async () => {
  const { onApply, onPendingChange, onSelect } = setup()
  await userEvent.click(screen.getByRole('button', { name: 'Edit Value' }))
  expect(onSelect).toHaveBeenCalled()
  const input = screen.getByRole('textbox', { name: 'Value' })
  expect(input).toHaveFocus()
  await userEvent.clear(input)
  await userEvent.type(input, 'Correction{Enter}')
  expect(onApply).toHaveBeenLastCalledWith('name', 'Correction')
  expect(screen.getByRole('button', { name: 'Edit Value' })).toHaveFocus()
  await userEvent.keyboard('{Enter}')
  await userEvent.type(screen.getByRole('textbox'), 'discard{Escape}')
  expect(onApply).toHaveBeenCalledTimes(1)
  expect(onPendingChange).toHaveBeenLastCalledWith('name', null)
  expect(screen.getByRole('button', { name: 'Edit Value' })).toHaveFocus()
})

test.each([false, true])('Tab moves naturally and applies (reverse=%s)', async (reverse) => {
  const { onApply } = setup()
  await userEvent.click(screen.getByRole('button', { name: 'Edit Value' }))
  await userEvent.type(screen.getByRole('textbox'), ' changed')
  await userEvent.tab({ shift: reverse })
  expect(onApply).toHaveBeenLastCalledWith('name', 'Original changed')
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  if (!reverse) expect(screen.getByRole('button', { name: 'Next' })).toHaveFocus()
})

test('invalid blur retains text and accessible error; Escape discards it', async () => {
  const { onApply, onPendingChange } = setup(true)
  await userEvent.click(screen.getByRole('button', { name: 'Edit Value' }))
  const input = screen.getByRole('textbox')
  await userEvent.clear(input)
  await userEvent.click(screen.getByRole('button', { name: 'Next' }))
  expect(input).toHaveValue('')
  expect(input).toHaveAttribute('aria-invalid', 'true')
  expect(input).toHaveAccessibleDescription('List items must not be blank.')
  expect(onApply).not.toHaveBeenCalled()
  expect(onPendingChange).toHaveBeenLastCalledWith('needs/0', { text: '', error: 'List items must not be blank.' })
  await userEvent.click(input)
  await userEvent.keyboard('{Escape}')
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('IME Enter does not apply; valid correction clears an earlier error', async () => {
  const { onApply } = setup(true)
  await userEvent.click(screen.getByRole('button', { name: 'Edit Value' }))
  const input = screen.getByRole('textbox')
  fireEvent.keyDown(input, { key: 'Enter', isComposing: true })
  expect(onApply).not.toHaveBeenCalled()
  await userEvent.clear(input)
  await userEvent.keyboard('{Enter}')
  expect(screen.getByRole('alert')).toBeInTheDocument()
  await userEvent.type(input, 'Fixed')
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  await userEvent.keyboard('{Enter}')
  expect(onApply).toHaveBeenLastCalledWith('needs/0', 'Fixed')
})


test('the edit button describes its displayed value, including after the value changes', () => {
  const props = { path: 'name' as const, label: 'Name', value: 'Original', displayValue: 'Original',
    onApply: vi.fn(), onPendingChange: vi.fn(), onSelect: vi.fn() }
  const { rerender } = render(<InlineDraftField {...props} />)
  expect(screen.getByRole('button', { name: 'Edit Name' })).toHaveAccessibleDescription('Original')
  rerender(<InlineDraftField {...props} value="Corrected" displayValue="Corrected" />)
  expect(screen.getByRole('button', { name: 'Edit Name' })).toHaveAccessibleDescription('Corrected')
})
