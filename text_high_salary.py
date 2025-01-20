def decorator_func(func):
    def wrapper(people):
        valid_people = []
        for person in people:
            if not isinstance(person.get('salary'), (int, float)) or person['salary'] is None:
                print(f"invalid salary for {person.get('name')}:{person.get('salary')}")
            else:
                valid_people.append(person)

        return func(valid_people)


    return wrapper   

@decorator_func
def high_salary(people):

    return [person for person in people if person['salary'] > 50000]


people = [
    {"name":"rrr", "salary":50000},
    {"name":"sss", "salary":55000},
    {"name":"ttt", "salary":49000},
    {"name":"uuu", "salary":None},
    {"name":"vvv", "salary":None},
]

high_salary_person = high_salary(people)
print(high_salary_person)
