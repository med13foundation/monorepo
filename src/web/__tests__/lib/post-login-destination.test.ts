import { resolvePostLoginDestination } from '@/lib/post-login-destination'
import { UserRole } from '@/types/auth'

describe('resolvePostLoginDestination', () => {
  it('defaults admins to dashboard', () => {
    expect(resolvePostLoginDestination(null, UserRole.ADMIN)).toBe('/dashboard')
  })

  it('defaults non-admin users to spaces', () => {
    expect(resolvePostLoginDestination(null, UserRole.VIEWER)).toBe('/spaces')
    expect(resolvePostLoginDestination(null, UserRole.RESEARCHER)).toBe('/spaces')
  })

  it('preserves non-admin callback URLs for allowed pages', () => {
    expect(
      resolvePostLoginDestination('/spaces/space-1', UserRole.VIEWER),
    ).toBe('/spaces/space-1')
  })

  it('reroutes non-admin users away from admin-only paths', () => {
    expect(
      resolvePostLoginDestination('/dashboard', UserRole.VIEWER),
    ).toBe('/spaces')
    expect(
      resolvePostLoginDestination(
        'http://localhost:3000/system-settings',
        UserRole.CURATOR,
      ),
    ).toBe('/spaces')
    expect(
      resolvePostLoginDestination('/admin/dictionary', UserRole.RESEARCHER),
    ).toBe('/spaces')
  })

  it('keeps admin-only callback URLs for admins', () => {
    expect(
      resolvePostLoginDestination('/dashboard', UserRole.ADMIN),
    ).toBe('/dashboard')
    expect(
      resolvePostLoginDestination('/admin/dictionary', UserRole.ADMIN),
    ).toBe('/admin/dictionary')
  })
})
