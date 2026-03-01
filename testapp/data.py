"""
Employee performance & attrition dataset for testing fiat-lux-agents.
150 records generated with a fixed seed — reproducible on every import.

Built-in relationships (good for ML / regression / classification):
- salary        ~ role, department, tenure, education, performance_score
- bonus_pct     ~ performance_score (strong positive)
- churn         ~ satisfaction_score (negative), salary_ratio (negative)
- promoted      ~ performance_score + tenure (threshold effect)
- absences      ~ satisfaction_score (negative)
- projects_completed ~ hours_per_week, performance_score
- training_hours ~ performance_score (positive, bidirectional)
- performance_score ~ tenure, education, training_hours

Good regression targets:  salary, bonus_pct, performance_score
Good classification targets: churned (bool), promoted (bool)
Good clustering dimensions:  department × role × performance × satisfaction
"""

import random

random.seed(42)

_DEPARTMENTS = ['Engineering', 'Sales', 'Marketing', 'Operations', 'Finance', 'HR']
_ROLES       = ['Junior', 'Mid', 'Senior', 'Lead', 'Manager']
_EDUCATION   = ['High School', "Bachelor's", "Master's", 'PhD']
_REVIEWS     = ['Below Expectations', 'Meets Expectations', 'Exceeds Expectations']

_FIRST = [
    'Alice', 'Bob', 'Carol', 'Dave', 'Eve', 'Frank', 'Grace', 'Hank',
    'Ivy', 'Jack', 'Karen', 'Leo', 'Mia', 'Ned', 'Olivia', 'Paul',
    'Quinn', 'Rosa', 'Sam', 'Tina', 'Uma', 'Victor', 'Wendy', 'Xander',
    'Yara', 'Zoe', 'Aaron', 'Beth', 'Chris', 'Diana', 'Ethan', 'Fiona',
    'George', 'Helen', 'Ivan', 'Julia', 'Kevin', 'Laura', 'Marcus', 'Nina',
]
_LAST = [
    'Smith', 'Jones', 'Williams', 'Brown', 'Davis', 'Miller', 'Wilson',
    'Moore', 'Taylor', 'Anderson', 'Thomas', 'Jackson', 'White', 'Harris',
    'Martin', 'Garcia', 'Lee', 'Clark', 'Lewis', 'Hall', 'Young', 'Allen',
    'King', 'Wright', 'Scott', 'Green', 'Baker', 'Adams', 'Nelson', 'Carter',
]

# Base salary by role
_ROLE_BASE = {'Junior': 55000, 'Mid': 75000, 'Senior': 95000, 'Lead': 115000, 'Manager': 130000}

# Department salary multiplier
_DEPT_MULT = {
    'Engineering': 1.20, 'Finance': 1.10, 'Sales': 1.05,
    'Marketing': 0.95,  'Operations': 0.90, 'HR': 0.88,
}

# Remote likelihood by department
_REMOTE_PROB = {
    'Engineering': 0.60, 'Marketing': 0.45, 'Finance': 0.35,
    'HR': 0.30, 'Sales': 0.25, 'Operations': 0.20,
}

_EDU_IDX = {'High School': 0, "Bachelor's": 1, "Master's": 2, 'PhD': 3}

_EDU_WEIGHTS = {
    'Junior':  [10, 50, 30, 10],
    'Mid':     [5,  45, 35, 15],
    'Senior':  [2,  35, 45, 18],
    'Lead':    [1,  25, 50, 24],
    'Manager': [5,  40, 40, 15],
}


def _generate(n=150):
    records = []
    used_names = set()

    for i in range(1, n + 1):
        role     = random.choices(_ROLES, weights=[30, 35, 20, 10, 5])[0]
        role_idx = _ROLES.index(role)
        dept     = random.choice(_DEPARTMENTS)

        # Age and tenure correlated with seniority
        min_age    = 22 + role_idx * 3
        age        = random.randint(min_age, min(58, min_age + 18))
        min_tenure = role_idx * 1.5
        max_tenure = max(min_tenure + 0.5, min(20.0, float(age - 21)))
        tenure     = round(random.uniform(max(0.5, min_tenure), max_tenure), 1)
        hire_year  = 2024 - int(tenure)

        education = random.choices(_EDUCATION, weights=_EDU_WEIGHTS[role])[0]
        edu_idx   = _EDU_IDX[education]

        remote = 'yes' if random.random() < _REMOTE_PROB[dept] else 'no'

        # Performance: tenure + education push baseline up
        perf = round(max(1.0, min(5.0,
            2.5 + tenure * 0.05 + edu_idx * 0.15 + random.gauss(0, 0.6)
        )), 1)

        satisfaction = round(max(1.0, min(10.0, random.gauss(6.5, 1.8))), 1)

        hours = round(max(30.0, min(65.0,
            random.gauss(40 + role_idx * 1.5 - (1.5 if remote == 'yes' else 0), 4)
        )), 1)

        training_hours     = max(0, min(80, int(perf * 8 + random.gauss(0, 10))))
        projects_completed = max(0, int((hours - 35) * 0.3 + perf * 2 + random.gauss(0, 2)))
        absences           = max(0, min(25, int(random.gauss(15 - satisfaction * 1.2, 3))))

        # Salary: role base × dept × tenure + education + perf bumps + noise
        salary = (
            _ROLE_BASE[role] * _DEPT_MULT[dept]
            + tenure * 1200
            + edu_idx * 3000
            + perf * 2000
            + random.gauss(0, 4000)
        )
        salary    = round(max(38000.0, salary), 2)
        bonus_pct = round(max(0.0, min(30.0, perf * 3 + random.gauss(0, 2))), 1)

        # Last review derived from performance
        if perf >= 4.0:
            rv_w = [5, 30, 65]
        elif perf >= 2.5:
            rv_w = [15, 65, 20]
        else:
            rv_w = [60, 35, 5]
        last_review = random.choices(_REVIEWS, weights=rv_w)[0]

        # Promotion: threshold on perf + tenure
        if perf >= 4.0 and tenure >= 2:
            promo_p = 0.45
        elif perf >= 3.0 and tenure >= 3:
            promo_p = 0.20
        elif tenure >= 5:
            promo_p = 0.10
        else:
            promo_p = 0.02
        promoted = random.random() < promo_p

        # Churn: driven by low satisfaction + below-market salary
        expected = _ROLE_BASE[role] * _DEPT_MULT[dept]
        churn_p  = 0.05
        if satisfaction < 4.0:
            churn_p += 0.30
        elif satisfaction < 6.0:
            churn_p += 0.12
        if salary / expected < 0.88:
            churn_p += 0.18
        if role == 'Junior' and tenure > 3:
            churn_p += 0.10
        churned = random.random() < min(0.72, churn_p)

        # Unique name
        while True:
            name = f"{random.choice(_FIRST)} {random.choice(_LAST)}"
            if name not in used_names:
                used_names.add(name)
                break

        records.append({
            'id':                  i,
            'name':                name,
            'department':          dept,
            'role':                role,
            'age':                 age,
            'tenure_years':        tenure,
            'hire_year':           hire_year,
            'education':           education,
            'remote':              remote,
            'hours_per_week':      hours,
            'projects_completed':  projects_completed,
            'training_hours':      training_hours,
            'absences':            absences,
            'performance_score':   perf,
            'satisfaction_score':  satisfaction,
            'salary':              salary,
            'bonus_pct':           bonus_pct,
            'last_review':         last_review,
            'promoted':            promoted,
            'churned':             churned,
        })

    return records


SAMPLE_DATA = _generate(150)

SCHEMA = """Columns:
- id (int): unique row identifier
- name (str): employee name
- department (str): Engineering | Sales | Marketing | Operations | Finance | HR
- role (str): Junior | Mid | Senior | Lead | Manager
- age (int): employee age in years (22–58)
- tenure_years (float): years at company (0.5–20)
- hire_year (int): year hired (2004–2024)
- education (str): High School | Bachelor's | Master's | PhD
- remote (str): yes | no — whether employee works remotely
- hours_per_week (float): average hours worked per week (30–65)
- projects_completed (int): projects completed in the past year
- training_hours (int): training hours completed in the past year (0–80)
- absences (int): days absent in the past year (0–25)
- performance_score (float): annual review score (1.0–5.0)
- satisfaction_score (float): employee satisfaction survey (1.0–10.0)
- salary (float): annual base salary in USD
- bonus_pct (float): bonus as % of base salary (0–30)
- last_review (str): Below Expectations | Meets Expectations | Exceeds Expectations
- promoted (bool): whether employee was promoted in the past year
- churned (bool): whether employee left the company

Built-in signal:
- salary ~ role, department, tenure_years, education, performance_score
- bonus_pct ~ performance_score (strong)
- churned ~ satisfaction_score (negative), salary vs expected (negative)
- promoted ~ performance_score + tenure_years (threshold)
- absences ~ satisfaction_score (negative)
"""

SUMMARY = {
    "total_rows": 150,
    "columns": [
        "id", "name", "department", "role", "age", "tenure_years", "hire_year",
        "education", "remote", "hours_per_week", "projects_completed",
        "training_hours", "absences", "performance_score", "satisfaction_score",
        "salary", "bonus_pct", "last_review", "promoted", "churned",
    ],
    "departments": ["Engineering", "Sales", "Marketing", "Operations", "Finance", "HR"],
    "roles":       ["Junior", "Mid", "Senior", "Lead", "Manager"],
    "education":   ["High School", "Bachelor's", "Master's", "PhD"],
    "statuses":    ["promoted", "churned"],
    "salary_range": [38000, 175000],
}
