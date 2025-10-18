# Effective Current Date Architecture

## Overview

The `effective_current_date` feature allows users to view portfolio data as of a specific date, enabling historical analysis and time-travel functionality across the application.

---

## Architecture Components

### **Backend**

#### 1. **Session Storage** (Primary Storage)
- **Location**: Django session (`request.session["effective_current_date"]`)
- **Format**: ISO date string (`"YYYY-MM-DD"`)
- **Scope**: Per-user, persists across requests
- **Lifecycle**: Initialized on first request, cleared on logout

#### 2. **Middleware** (`portfolio_management/middleware.py`)
```python
class InitializeEffectiveDateMiddleware:
    def __call__(self, request):
        if "effective_current_date" not in request.session:
            request.session["effective_current_date"] = date.today().isoformat()
            request.session.modified = True
```
**Purpose**: Ensures every request has an effective current date (defaults to today)

#### 3. **API Endpoints**

**GET `/api/effective-current-date/`** (`common/views.py`)
```python
@api_view(["GET"])
def get_effective_current_date(request):
    effective_current_date = request.session.get(
        "effective_current_date", datetime.now().date().isoformat()
    )
    return Response({"effective_current_date": effective_current_date})
```
**Purpose**: Retrieve current effective date from session

**POST `/users/api/update_dashboard_settings/`** (`users/views.py`)
```python
@action(detail=False, methods=["POST"])
def update_dashboard_settings(self, request):
    # ... validate and save User model fields ...

    # Save table_date to session (it's not a User model field)
    if "table_date" in request.data:
        request.session["effective_current_date"] = request.data["table_date"]
        request.session.modified = True

    # Return response with the session value
    response_data = serializer.data
    response_data["table_date"] = request.session.get("effective_current_date")

    return Response(response_data)
```
**Purpose**: Update effective current date in session

**POST `/users/api/logout/`** (`users/views.py`)
```python
@action(detail=False, methods=["POST"])
def logout(self, request):
    # ... blacklist token ...

    # Clear session data (including effective_current_date)
    request.session.flush()

    return Response({"success": "Logged out successfully."})
```
**Purpose**: Clear session on logout, resetting effective current date

#### 4. **Usage in Views**

All views that need date-based filtering retrieve from session:
```python
effective_current_date = request.session.get(
    "effective_current_date", datetime.now().date().isoformat()
)
```

Examples:
- `api_get_security_price_history` (database/views.py)
- `api_get_security_position_history` (database/views.py)
- `api_get_security_transactions` (database/views.py)
- `get_year_options_api` (common/views.py)
- `get_positions_table_api` (core/positions_utils.py)
- `get_security_detail` (core/securities_utils.py)

---

### **Frontend**

#### 1. **Vuex Store** (`portfolio-frontend/src/store/index.js`)

**State**:
```javascript
state: {
  effectiveCurrentDate: null,
  // ...
}
```

**Mutations**:
```javascript
mutations: {
  SET_EFFECTIVE_CURRENT_DATE(state, date) {
    state.effectiveCurrentDate = date
  }
}
```

**Actions**:
```javascript
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

#### 2. **Settings Dialog** (`portfolio-frontend/src/components/SettingsDialog.vue`)

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

#### 3. **Component Usage**

Components access the date via computed property:
```javascript
const effectiveCurrentDate = computed(() => store.state.effectiveCurrentDate)
```

Examples:
- `SecurityDetailPage.vue` - for price/position charts
- `TransactionsPage.vue` - for transaction filtering
- `OpenPositionsPage.vue` - for portfolio positions

---

## Data Flow

### **Setting the Date**

```mermaid
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

### **Retrieving the Date**

```mermaid
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

### **Resetting on Logout**

```mermaid
User clicks Logout
    ↓
Frontend: Call logout API
    ↓
Backend: POST /users/api/logout/
    ↓
Backend: Token blacklisted
    ↓
Backend: request.session.flush() - clears all session data
    ↓
Frontend: Redirect to login page
    ↓
Next Login: Middleware initializes with today's date
```

---

## Key Design Decisions

### **Why Session Storage?**

✅ **Pros**:
- Per-user, server-side storage
- Persists across page refreshes
- No additional database queries
- Automatic cleanup on logout

❌ **Alternatives Considered**:
- ~~User model field~~ - Would persist across sessions (undesired)
- ~~LocalStorage~~ - Would persist across logout (undesired)
- ~~URL params~~ - Would not persist across navigation

### **Why Not a User Model Field?**

The effective current date is a **session-scoped preference**, not a **persistent user setting**. We want it to:
- Reset to "today" when user logs in again
- Not persist across sessions
- Be independent per browser/device

### **Why Clear on Logout?**

This ensures a clean slate for each login session:
- User always starts with "today" view
- No confusion from old date settings
- Consistent behavior across devices

---

## Implementation Checklist

### Backend ✅

- [x] Middleware initializes session with today's date
- [x] `update_dashboard_settings` saves to session
- [x] `update_dashboard_settings` returns session value in response
- [x] `logout` clears session with `request.session.flush()`
- [x] All views retrieve from session consistently

### Frontend ✅

- [x] Vuex store has `effectiveCurrentDate` state
- [x] Actions for fetching and updating date
- [x] Settings dialog updates backend and store
- [x] Components don't reset date on unmount
- [x] Data refresh triggered after date change

---

## Common Issues & Solutions

### **Issue: Date resets to today when navigating**
**Cause**: Component's `onBeforeUnmount` was resetting the date
**Solution**: Remove reset logic from component lifecycle hooks

### **Issue: Date not persisting after update**
**Cause**: Backend wasn't saving to session
**Solution**: Add session save logic in `update_dashboard_settings`

### **Issue: Different dates in different components**
**Cause**: Components fetching independently
**Solution**: Use Vuex store as single source of truth

---

## Testing

### **Manual Testing**

1. **Set Date**: Open settings, change date, verify it persists across pages
2. **Page Refresh**: Refresh browser, verify date still set
3. **Logout**: Logout and login, verify date resets to today
4. **Multiple Tabs**: Open multiple tabs, verify date syncs across tabs

### **Backend Testing**

```python
def test_effective_date_persistence(self):
    # Login
    self.client.login(username='testuser', password='testpass')

    # Set date
    response = self.client.post('/users/api/update_dashboard_settings/', {
        'table_date': '2024-01-15'
    })
    self.assertEqual(response.data['table_date'], '2024-01-15')

    # Verify persistence
    response = self.client.get('/api/effective-current-date/')
    self.assertEqual(response.data['effective_current_date'], '2024-01-15')

    # Logout
    self.client.post('/users/api/logout/', {'refresh_token': token})

    # Login again
    self.client.login(username='testuser', password='testpass')

    # Verify reset to today
    response = self.client.get('/api/effective-current-date/')
    self.assertEqual(response.data['effective_current_date'], date.today().isoformat())
```

---

## Future Enhancements

### **Potential Improvements**

1. **Date History**: Track user's date selection history
2. **Quick Date Presets**: Add "Yesterday", "Last Week", "Last Month" shortcuts
3. **Date Range**: Support date ranges instead of single date
4. **Per-Page Dates**: Different effective dates for different pages
5. **Date Bookmarks**: Save favorite dates for quick access

### **Technical Debt**

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
