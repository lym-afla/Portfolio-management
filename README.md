# Portfolio Management System

This is a portfolio management application built with:
- Frontend: Vue.js 3 and Vuetify 3
- Backend: Django
- Database: SQLite

## Project Overview

This application allows users to manage and analyze their investment portfolio. It provides features for tracking open and closed positions, viewing dashboard summaries, and managing user profiles.

## Technologies Used

- Frontend:
  - Vue.js 3
  - Vuetify 3
- Backend:
  - Django
- Database:
  - SQLite
- Previously used (in old frontend):
  - HTML, CSS, JavaScript
  - Bootstrap
  - jQuery
  - DataTables
  - Chart.js

## Project Setup

1. Clone the repository:
   ```
   git clone https://github.com/lym-afla/Portfolio-management.git
   ```

2. Set up the backend:
   ```
   cd Portfolio-management/portfolio_management
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   pip install -r requirements.txt
   python manage.py migrate
   python manage.py runserver
   ```

3. Set up the frontend:
   ```
   cd ../portfolio_frontend
   npm install
   ```

### Development

To run the frontend in development mode with hot-reloads:
```
npm run serve
```

### Production Build

To compile and minify for production:
```
npm run build
```

### Linting

To lint and fix files:
```
npm run lint
```

## Folder Structure

portfolio_management/
├── portfolio_frontend/
│   ├── public/
│   ├── src/
│       ├── assets/
│       ├── components/
│           ├── BrokerSelection.vue
│           ├── DashboardSummary.vue
│           ├── LoginForm.vue
│           ├── Navigation.vue
│           ├── Profile.vue
│           ├── ProfileEdit.vue
│           ├── ProfileLayout.vue
│           ├── RegisterForm.vue
│       ├── router/
│           ├── index.js
│       ├── services/
│           ├── api.js
│       ├── store/
│           ├── index.js
│       ├── utils/
│           ├── auth.js
│           ├── brokerUtils.js
│           ├── formatter.js
│       ├── views/
│           ├── ClosedPositionsPage.vue
│           ├── DashboardPage.vue
│           ├── LoginPage.vue
│           ├── OpenPositionsPage.vue
│           ├── RegisterPage.vue
│       ├── App.vue
│       ├── main.js
│   ├── package.json
│   ├── package-lock.json
│   ├── vue.config.js
├── portfolio_management/
│   ├── closed_positions/
│       ├── migrations/
│       ├── templates/
│           ├── closed_positions.html
│           ├── closed_positions_tbody.html
│           ├── closed_positions_tfoot.html
│       ├── urls.py
│       ├── views.py
│   ├── common/
│       ├── migrations/
│       ├── templatetags/
│           ├── custom_filters.py
│       ├── apps.py
│       ├── forms.py
│       ├── models.py
│       ├── tests.py
│       ├── views.py
│   ├── dashboard/
│       ├── migrations/
│       ├── templates/
│           ├── dashboard.html
│       ├── urls.py
│       ├── views.py
│   ├── database/
│       ├── migrations/
│       ├── templates/
│           ├── brokers.html
│           ├── database.html
│           ├── prices.html
│           ├── securities.html
│       ├── forms.py
│       ├── urls.py
│       ├── views.py
│   ├── open_positions/
│       ├── migrations/
│       ├── templates/
│           ├── open_positions.html
│           ├── open_positions_tbody.html
│           ├── open_positions_tfoot.html
│       ├── urls.py
│       ├── views.py
│   ├── portfolio_management/
│       ├── middleware.py
│       ├── settings.py
│       ├── urls.py
│       ├── wsgi.py
│   ├── static/
│       ├── css/
│           ├── styles.css
│       ├── icons/
│           ├── icon.png
│       ├── js/
│           ├── closed-positions.js
│           ├── dashboard.js
│           ├── edit-delete.js
│           ├── formHandler.js
│           ├── nav-chart.js
│           ├── open-positions.js
│           ├── price-import.js
│           ├── profile_settings.js
│           ├── sidebar.js
│           ├── summary.js
│           ├── transaction-form.js
│   ├── summary_analysis/
│       ├── migrations/
│       ├── templates/
│           ├── summary.html
│       ├── urls.py
│       ├── views.py
│   ├── templates/
│       ├── registration/
│           ├── login.html
│           ├── logout.html
│           ├── signup.html
│       ├── snippets/
│           ├── broker_selection_header.html
│           ├── buttons-settings-header.html
│           ├── handle_database_item.html
│       ├── layout.html
│   ├── transactions/
│       ├── migrations/
│       ├── templates/
│           ├── transactions.html
│       ├── urls.py
│       ├── views.py
│   ├── users/
│       ├── migrations/
│       ├── templates/
│           ├── profile.html
│           ├── profile_edit.html
│           ├── profile_layout.html
│       ├── forms.py
│       ├── models.py
│       ├── serializers.py
│       ├── urls.py
│       ├── views.py
│   ├── constants.py
│   ├── db.sqlite3
│   ├── manage.py
│   ├── pytest.ini
│   ├── test_utils.py
│   ├── utils.py
├── .cursorignore
├── .gitignore
├── .cursorrules
├── README.md
├── requirements.txt

## Features

- User authentication (login, registration, profile management)
- Dashboard with portfolio summary
- Open positions tracking
- Closed positions history
- Broker selection
- Data import and export capabilities

## API Integration

The Vue.js frontend integrates with the Django backend through RESTful API endpoints. Key endpoints include:

- `/api/auth/`: User authentication
- `/api/portfolio/`: Portfolio data
- `/api/transactions/`: Transaction management

For full API documentation, please refer to the backend codebase.

## Deployment

[Add deployment instructions here, e.g., how to deploy to a production server]

## License

[Specify the license, e.g., MIT License, GNU GPL, etc.]

## Contributing

[If you want to accept contributions, add guidelines here]

### Customize Configuration
For detailed explanation on how things work, check out the [Configuration Reference](https://cli.vuejs.org/config/).