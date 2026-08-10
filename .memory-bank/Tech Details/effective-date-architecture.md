# Effective Current Date Architecture

## Overview

The `effective_current_date` feature enables users to view portfolio data as of a specific historical date, providing time-travel functionality across the application. This architecture uses session-based storage to maintain per-user, session-scoped date preferences.

---

## Architecture Components

### Backend Implementation

#### Session Storage (Primary Storage)
- **Location**: Django session (`request.session["effective_current_date"]`)
- **Format**: ISO date string (`"YYYY-MM-DD"`)
- **Scope**: Per-user, persists across requests
- **Lifecycle**: Initialized on first request, cleared on logout

#### Middleware (`portfolio_management/middleware.py`)
```python
class InitializeEffectiveDateMiddleware:
    def __call__(self, request):
        if "effective_current_date" not in request.session:
            request.session["effective_current_date"] = date.today().isoformat()
            request.session.modified = True
```
**Purpose**: Ensures every request has an effective current date (defaults to today)

#### API Endpoints

**GET `/api/effective-current-date/`** (`common/views.py`)
```python
@api_view(["GET"])
def get_effective_current_date(request):
    effective_current_date = request.session.get(
        "effective_current_date", datetime.now().date().isoformat()
    )
    return Response({"effective_current_date": effective_current_date})
```

**POST `/users/api/update_dashboard_settings/`** (`users/views.py`)
```python
@action(detail=False, methods=["POST"])
def update_dashboard_settings(self, request):
    # Save table_date to session (it's not a User model field)
    if "table_date" in request.data:
        request.session["effective_current_date"] = request.data["table_date"]
        request.session.modified = True

    # Return response with the session value
    response_data = serializer.data
    response_data["table_date"] = request.session.get("effective_current_date")
    return Response(response_data)
```

**POST `/users/api/logout/`** (`users/views.py`)
```python
@action(detail=False, methods=["POST"])
def logout(self, request):
    # Clear session data (including effective_current_date)
    request.session.flush()
    return Response({"success": "Logged out successfully."})
```

### Frontend Implementation

#### Vuex Store (`portfolio-frontend/src/store/index.js`)
```javascript
state: {
  effectiveCurrentDate: null,
}

mutations: {
  SET_EFFECTIVE_CURRENT_DATE(state, date) {
    state.effectiveCurrentDate = date
  }
}

actions: {
  async fetchEffectiveCurrentDate({ commit }) {
    const response = await api.getEffectiveCurrentDate()
    commit('SET_EFFECTIVE_CURRENT_DATE', response.effective_current_date)
  },
  updateEffectiveCurrentDate({ commit }, date) {
    commit('SET_EFFECTIVE_CURRENT_DATE', date)
  }
}
```

#### Settings Dialog (`portfolio-frontend/src/components/SettingsDialog.vue`)
User interface for changing the effective current date:
```javascript
const saveSettings = async () => {
  const response = await updateDashboardSettings(formData)

  // Update store with new date from response
  store.dispatch('updateEffectiveCurrentDate', response.table_date)

  // Trigger data refresh across application
  store.dispatch('triggerDataRefresh')
}
```

---

## Key Design Decisions

### Why Session Storage?

✅ **Benefits**:
- Per-user, server-side storage
- Persists across page refreshes
- No additional database queries
- Automatic cleanup on logout

❌ **Rejected Alternatives**:
- ~~User model field~~ - Would persist across sessions (undesired)
- ~~LocalStorage~~ - Would persist across logout (undesired)
- ~~URL params~~ - Would not persist across navigation

### Session-Scoped vs Persistent Setting

The effective current date is intentionally **session-scoped**, not a **persistent user setting**:
- Resets to "today" when user logs in again
- Does not persist across sessions
- Independent per browser/device

### Data Flow Patterns

#### Setting the Date
```
User Input (Settings Dialog)
    ↓
Frontend: SettingsDialog.vue calls updateDashboardSettings()
    ↓
Backend: POST /users/api/update_dashboard_settings/
    ↓
Backend: Save to request.session["effective_current_date"]
    ↓
Backend: Return response with table_date
    ↓
Frontend: store.dispatch('updateEffectiveCurrentDate', response.table_date)
    ↓
Frontend: Vuex state updated
    ↓
All components re-render with new date
```

#### Retrieving the Date
```
Page Load / Navigation
    ↓
Frontend: Component checks if effectiveCurrentDate in store
    ↓
If null: store.dispatch('fetchEffectiveCurrentDate')
    ↓
Backend: GET /api/effective-current-date/
    ↓
Backend: Read from request.session["effective_current_date"]
    ↓
Frontend: Vuex state updated
    ↓
Component uses computed property: effectiveCurrentDate
```

#### Resetting on Logout
```
User clicks Logout
    ↓
Frontend: Call logout API
    ↓
Backend: POST /users/api/logout/
    ↓
Backend: request.session.flush() - clears all session data
    ↓
Frontend: Redirect to login page
    ↓
Next Login: Middleware initializes with today's date
```

---

## Usage in Views

All views that need date-based filtering retrieve from session:
```python
effective_current_date = request.session.get(
    "effective_current_date", datetime.now().date().isoformat()
)
```

**Examples of views using effective date:**
- `api_get_security_price_history` (database/views.py)
- `api_get_security_position_history` (database/views.py)
- `api_get_security_transactions` (database/views.py)
- `get_year_options_api` (common/views.py)
- `get_positions_table_api` (core/positions_utils.py)
- `get_security_detail` (core/securities_utils.py)

**Frontend components using effective date:**
- `SecurityDetailPage.vue` - for price/position charts
- `TransactionsPage.vue` - for transaction filtering
- `OpenPositionsPage.vue` - for portfolio positions

---

## Implementation Guidelines

### Backend Development
When adding new date-sensitive views:
1. Always retrieve effective date from session
2. Provide fallback to today's date
3. Ensure consistent date format (ISO string)
4. Consider timezone implications

### Frontend Development
When creating components that use effective date:
1. Access via computed property from Vuex store
2. Trigger data refresh when date changes
3. Don't reset date in component lifecycle hooks
4. Use consistent date formatting

### Testing Requirements
- Test date persistence across page refreshes
- Verify date resets on logout
- Test date changes trigger data refresh
- Verify consistent date formatting across components

---

## Common Issues & Solutions

### Issue: Date resets to today when navigating
**Cause**: Component's `onBeforeUnmount` was resetting the date
**Solution**: Remove reset logic from component lifecycle hooks

### Issue: Date not persisting after update
**Cause**: Backend wasn't saving to session
**Solution**: Add session save logic in `update_dashboard_settings`

### Issue: Different dates in different components
**Cause**: Components fetching independently
**Solution**: Use Vuex store as single source of truth

---

## Future Enhancements

### Potential Improvements
1. **Date History**: Track user's date selection history
2. **Quick Date Presets**: Add "Yesterday", "Last Week", "Last Month" shortcuts
3. **Date Range**: Support date ranges instead of single date
4. **Per-Page Dates**: Different effective dates for different pages
5. **Date Bookmarks**: Save favorite dates for quick access

### Technical Debt
- Consider moving session logic to a dedicated service class
- Add caching layer for frequently accessed dates
- Implement WebSocket notifications for date changes across tabs

---

## References

- **Django Sessions**: https://docs.djangoproject.com/en/stable/topics/http/sessions/
- **Vuex State Management**: https://vuex.vuejs.org/
- **Middleware Documentation**: https://docs.djangoproject.com/en/stable/topics/http/middleware/

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-10-09 | Initial implementation with session storage |
| 1.1 | 2025-10-09 | Fixed persistence issue - added session save in update_dashboard_settings |
| 1.2 | 2025-10-09 | Added logout session clear functionality |
