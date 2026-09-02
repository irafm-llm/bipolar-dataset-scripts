# One canonical RU and UK rendering per English opener (F8).
# All 30 are distinct within each language, so the opener stays recoverable from the text.
# Two are meaning corrections, not just consistency picks:
#   "These days"  RU "В эти дни"/UK "Цими днями" named a bounded period, not 'nowadays'
#   "Right now"   UK "Просто зараз" is a calque of RU "прямо сейчас"
#   UK "These days" is "У наші дні", a direct parallel of the Russian (blind-gate fix B)
CANON = {
 # Past
 "In 2021":                    ("В 2021 году",          "У 2021 році"),
 "In 2022":                    ("В 2022 году",          "У 2022 році"),
 "In 2023":                    ("В 2023 году",          "У 2023 році"),
 "In 2024":                    ("В 2024 году",          "У 2024 році"),
 "Last year":                  ("В прошлом году",       "Минулого року"),
 "Last month":                 ("В прошлом месяце",     "Минулого місяця"),
 "Last winter":                ("Прошлой зимой",        "Минулої зими"),
 "Earlier this year":          ("Ранее в этом году",    "Раніше цього року"),
 "Two years ago":              ("Два года назад",       "Два роки тому"),
 "During the previous spring": ("Прошлой весной",       "Минулої весни"),
 # Present
 "Today":                      ("Сегодня",              "Сьогодні"),
 "This week":                  ("На этой неделе",       "Цього тижня"),
 "This month":                 ("В этом месяце",        "Цього місяця"),
 "Right now":                  ("Прямо сейчас",         "Саме зараз"),
 "At present":                 ("В настоящее время",    "Наразі"),
 "These days":                 ("В наши дни",           "У наші дні"),
 "Currently":                  ("Сейчас",               "Нині"),
 "This morning":               ("Сегодня утром",        "Сьогодні вранці"),
 "This afternoon":             ("Сегодня днём",         "Сьогодні вдень"),
 "Tonight":                    ("Сегодня вечером",      "Сьогодні ввечері"),
 # Future
 "Tomorrow":                   ("Завтра",               "Завтра"),
 "Next week":                  ("На следующей неделе",  "Наступного тижня"),
 "Next month":                 ("В следующем месяце",   "Наступного місяця"),
 "Later this year":            ("Позже в этом году",    "Пізніше цього року"),
 "Next year":                  ("В следующем году",     "Наступного року"),
 "In the coming weeks":        ("В ближайшие недели",   "Найближчими тижнями"),
 "Soon":                       ("Вскоре",               "Незабаром"),
 "In the near future":         ("В ближайшем будущем",  "Найближчим часом"),
 "By the end of the year":     ("К концу года",         "До кінця року"),
 "In 2027":                    ("В 2027 году",          "У 2027 році"),
}
EN_SORTED=sorted(CANON,key=len,reverse=True)
def en_opener(sentence_en):
    for o in EN_SORTED:
        if sentence_en.startswith(o+","): return o
    return None
assert len({v[0] for v in CANON.values()})==30, 'RU openers must be distinct'
assert len({v[1] for v in CANON.values()})==30, 'UK openers must be distinct'
