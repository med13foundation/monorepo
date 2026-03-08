import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SpaceMembersList } from '@/components/research-spaces/SpaceMembersList'
import { MembershipRole, type ResearchSpaceMembership } from '@/types/research-space'

function buildMembership(
  overrides: Partial<ResearchSpaceMembership> = {},
): ResearchSpaceMembership {
  return {
    id: 'membership-1',
    space_id: 'space-1',
    user_id: 'user-1',
    role: MembershipRole.RESEARCHER,
    invited_by: null,
    invited_at: null,
    joined_at: '2026-03-07T00:00:00Z',
    is_active: true,
    created_at: '2026-03-07T00:00:00Z',
    updated_at: '2026-03-07T00:00:00Z',
    ...overrides,
  }
}

describe('SpaceMembersList', () => {
  beforeAll(() => {
    HTMLElement.prototype.hasPointerCapture = HTMLElement.prototype.hasPointerCapture ?? (() => false)
    HTMLElement.prototype.setPointerCapture = HTMLElement.prototype.setPointerCapture ?? (() => undefined)
    HTMLElement.prototype.releasePointerCapture =
      HTMLElement.prototype.releasePointerCapture ?? (() => undefined)
    Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => undefined)
  })

  it('lets managers assign a research-space role from the member table', async () => {
    const user = userEvent.setup()
    const onUpdateRole = jest.fn()

    render(
      <SpaceMembersList
        memberships={[buildMembership()]}
        isLoading={false}
        errorMessage={null}
        canManage
        onUpdateRole={onUpdateRole}
      />,
    )

    const row = screen.getByText('user-1').closest('tr')
    expect(row).not.toBeNull()

    const rowScope = within(row as HTMLTableRowElement)
    await user.click(rowScope.getByRole('combobox'))
    await user.click(screen.getByRole('option', { name: 'Admin' }))

    expect(onUpdateRole).toHaveBeenCalledWith('membership-1', MembershipRole.ADMIN)
  })

  it('keeps owner memberships read-only in the role column', () => {
    render(
      <SpaceMembersList
        memberships={[
          buildMembership({
            id: 'membership-owner',
            user_id: 'owner-user',
            role: MembershipRole.OWNER,
          }),
        ]}
        isLoading={false}
        errorMessage={null}
        canManage
        onUpdateRole={jest.fn()}
      />,
    )

    const row = screen.getByText('owner-user').closest('tr')
    expect(row).not.toBeNull()

    const rowScope = within(row as HTMLTableRowElement)
    expect(rowScope.queryByRole('combobox')).not.toBeInTheDocument()
    expect(rowScope.getByText('Owner')).toBeInTheDocument()
  })
})
