// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CreateGroup } from '@/features/wireframes/GroupViews';

afterEach(cleanup);
describe('live creation form', () => {
  it('rejects blank-after-trimming names without discarding the draft', () => {
    const create = vi.fn();
    render(<CreateGroup live onCreate={create} onDemo={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('Give your group a name'), {
      target: { value: '   ' },
    });
    fireEvent.change(screen.getByLabelText('Your first name'), {
      target: { value: 'Alex' },
    });
    fireEvent.submit(
      screen
        .getByRole('button', { name: 'Create your group' })
        .closest('form')!,
    );
    expect(create).not.toHaveBeenCalled();
    expect(screen.getByRole('alert').textContent).toContain('Add a group name');
    expect(
      (screen.getByLabelText('Your first name') as HTMLInputElement).value,
    ).toBe('Alex');
  });
  it('matches server length limits and prevents another submit while creating', () => {
    const create = vi.fn();
    render(<CreateGroup live pending onCreate={create} onDemo={vi.fn()} />);
    expect(
      (screen.getByLabelText('Give your group a name') as HTMLInputElement)
        .maxLength,
    ).toBe(40);
    expect(
      (screen.getByRole('button', { name: 'Creating…' }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    fireEvent.submit(
      screen.getByRole('button', { name: 'Creating…' }).closest('form')!,
    );
    expect(create).not.toHaveBeenCalled();
  });
  it('keeps entered fields after an API failure so the user can retry', () => {
    const create = vi.fn();
    const ui = render(<CreateGroup live onCreate={create} onDemo={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('Give your group a name'), {
      target: { value: '  Shared chapter  ' },
    });
    fireEvent.change(screen.getByLabelText('Your first name'), {
      target: { value: ' Alex ' },
    });
    fireEvent.click(screen.getByRole('radio', { name: '2 people' }));
    fireEvent.submit(
      screen
        .getByRole('button', { name: 'Create your group' })
        .closest('form')!,
    );
    expect(create.mock.calls[0]![0]).toMatchObject({
      name: 'Shared chapter',
      size: 2,
      members: [{ name: 'Alex' }, { name: '' }],
    });
    ui.rerender(
      <CreateGroup
        live
        errorMessage="Please try again."
        onCreate={create}
        onDemo={vi.fn()}
      />,
    );
    expect(screen.getByRole('alert').textContent).toBe('Please try again.');
    expect(
      (screen.getByLabelText('Give your group a name') as HTMLInputElement)
        .value,
    ).toBe('  Shared chapter  ');
  });
});
