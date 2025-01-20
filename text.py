def high_salary(people):

    return [person for person in people if person['salary'] > 50000]


people = [
    {"name":"rrr", "salary":50000},
    {"name":"sss", "salary":55000},
    {"name":"ttt", "salary":49000}
]


high_salary_person = high_salary(people)
print(high_salary_person)