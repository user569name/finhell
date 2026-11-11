from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ConfigDict

class FinanceBase:
    def __init__(self, time):
        self.time = time

# ФИКС 1: Добавлено наследование (FinanceBase), иначе super().__init__ упадет
class Dreaming_of_pokoi_in_rich(FinanceBase):
    def __init__(self,kollichestvo_babok,max_vigoda, time):
        super().__init__(time)
        self.kollichestvo_babok = kollichestvo_babok
        self.max_vigoda = max_vigoda



class Credit(BaseModel):
    money_for_new_home: float
    vznos: float
    procent_for_credit: float
    time: float


def logica_1(data: Credit):
    print("Введите данные для кредита: ")
    money_for_new_home = int(input("Сколько денег надо: "))
    vznos = float(input("Начальный взнос: "))
    procent_for_credit = float(input("Процент: "))
    time = int(input("Время в годах: "))
    sdelka = Credit(
        money_for_new_home = money_for_new_home,
        vznos=vznos,
        procent_for_credit=procent_for_credit,
        time=time
        )
    if sdelka.money_for_new_home * 0.1 <= sdelka.vznos:
        full_credit = sdelka.money_for_new_home - sdelka.vznos
        months = sdelka.time * 12
        list_1 = []
        ficha = []
        count = 0
        r = sdelka.procent_for_credit / 100 / 12
        kuski_credita = full_credit * r / (1 - (1 + r) ** (-months))
        full_price = kuski_credita * months
        pereplata = full_price - full_credit
        while count < months:
            list_1.append(kuski_credita)
            ficha.append(f"Выплата по кредиту №{count}: ")
            count += 1
        spisok_viplat = dict(zip(ficha, list_1))
        return {
                "Тело кредита": round(full_credit, 2),
                "Проценты": round(pereplata, 2),
                "Выплаты в месяц": round(kuski_credita, 2),
                **spisok_viplat}
    else:
        print("Начальный взнос меньше 10%")
        return {}


class Vclad(BaseModel):
    time: float
    nach_vlozhenie: float
    procent_for_vclad: float
    dodep: float
    step: int


def logica_2():
    print("Введите данные для кредита:")
    nach_vlozhenie = int(input("Сумма денюжек на вклад: "))
    procent_for_vclad = float(input("Процент: "))
    dodep = float(input("Пополнение: "))
    time = int(input("Всего время в месяцах: "))
    step = int(input("Проценты каждый этот промежуток времени: "))

    sdelka_vclad = Vclad(
        nach_vlozhenie=nach_vlozhenie,
        procent_for_vclad=procent_for_vclad,
        dodep=dodep,
        step=step,
        time=time
        )

    rate = sdelka_vclad.procent_for_vclad / 100 * sdelka_vclad.step / 12

    if sdelka_vclad.dodep == 0:
        n = int(sdelka_vclad.time / sdelka_vclad.step)
        pribyl_za_shag = sdelka_vclad.nach_vlozhenie * rate
        total_plus_babki = sdelka_vclad.nach_vlozhenie + (pribyl_za_shag * n)
        return {
                "Прибыль в месяц": pribyl_za_shag / sdelka_vclad.step,
                 "Итоговая сумма": total_plus_babki
                }
    else: # ФИКС 2: Убрана ветка == 67. Теперь любое пополнение работает корректно.
        luk_cat2 = []
        ficha = []
        n = int(sdelka_vclad.time / sdelka_vclad.step)
        balance = sdelka_vclad.nach_vlozhenie
        total_contrib = 0
        for i in range(n):
            pribyl = balance * rate
            balance += pribyl
            balance += sdelka_vclad.dodep
            total_contrib += sdelka_vclad.dodep
            luk_cat2.append(pribyl)
            ficha.append(f"Выплата по вкладу №{i}: ")
        pribavka = dict(zip(ficha, luk_cat2))
        net_profit = balance - sdelka_vclad.nach_vlozhenie - total_contrib
        return {
                "Прибыль в целом": net_profit,
                "Итоговая сумма": balance,
                **pribavka
                }


class OFZPD(BaseModel):
    time: float
    procent_ofz: float
    step_ofz: float
    money_for_ofz: float


def logica_3():
    money_for_ofz = float(input("Всего денег для офз: "))
    time = int(input("Колличество месяцев которое денюжка проледит в ОФЗ: "))
    procent_ofz = float(input("Процен для ОФЗ: "))
    step_ofz = float(input("Как часто начисляются проценты: "))
    predlozhenie = OFZPD(
        time=time,
        procent_ofz=procent_ofz,
        step_ofz=step_ofz,
        money_for_ofz=money_for_ofz
        )

    rate_ofz = predlozhenie.procent_ofz / 100 * predlozhenie.step_ofz / 12
    n = int(predlozhenie.time / predlozhenie.step_ofz)

    yami_plus = []
    ficha = []
    for i in range(n):
        plus_ofz = predlozhenie.money_for_ofz * rate_ofz
        yami_plus.append(plus_ofz)
        ficha.append(f"Выплата по офз №{i}: ")
    pribavka = dict(zip(ficha, yami_plus))
    return {
            "Прибыль в целом": sum(yami_plus),
            "Итоговая сумма": predlozhenie.money_for_ofz + sum(yami_plus),
            "Прибыль каждое некоторое время: ": yami_plus,
            **pribavka
            }


class Home(BaseModel):
    prise_for_home: float
    prise_for_m_2_home: float
    licvid: bool
    riski: float
    arenda: float
    time: float


def logica_4():
    prise_for_home = float(input("Введите цену дома: "))
    m_2 = float(input("Введите сколько кваратных метров: "))
    licvid = input("Новая хата? (да/нет): ").strip().lower() == "да"
    riski = float(input("Сколько будет стоить обслуживание этой квартиры в год: "))
    arenda = int(input("Сколько будет стоить аренда в начале без учета индексации: "))
    time = int(input("Насколько лет прогноз нужен: "))
    
    buy_dream = Home(
        prise_for_home=prise_for_home,
        prise_for_m_2_home=m_2, # ФИКС 3: было m_2=m_2, а нужно prise_for_m_2_home
        licvid=licvid,
        riski=riski,
        arenda=arenda,
        time=time
        )
        
    count = 0
    list_2 = []
    while count < buy_dream.time:
        if buy_dream.licvid == True:
            podorozhanie = buy_dream.prise_for_home * 0.125
            list_2.append(podorozhanie)
            count += 1
        else:
            podorozhanie = buy_dream.prise_for_home * 0.08
            list_2.append(podorozhanie)
            count += 1
    prybil = buy_dream.arenda * buy_dream.time
    obsluzhivanie = buy_dream.riski * buy_dream.time
    money_in_end = buy_dream.prise_for_home + sum(list_2) + prybil - obsluzhivanie
    return {
            "Общие плюс бабки": money_in_end,
            "Плюс бабки и квартира": prybil - obsluzhivanie
            }


# ФИКС 4: В Inflyaciya оставлены только те поля, которые используются при ее создании
class Inflyaciya(BaseModel):
    inf_procent: float
    time: float
    full_credit: float = 0
    pereplata_po_creditu: float = 0
    doxod_ot_vclada: float = 0 


def obescenivanie(
                   result_credit=None,
                   result_vclad=None,
                   result_ofzpd=None,
                   result_home=None,
                   ):
    result_credit = result_credit or {}
    result_vklad = result_vclad or {}
    result_ofzpd = result_ofzpd or {}
    result_home = result_home or {}

    print("Введите информацию об инфляцию: ")
    inf_procent = float(input("Процент: "))
    time = float(input("Введите время: "))
    pereplata_po_creditu = result_credit.get("Проценты", 0)
    doxod_ot_vclada = result_vclad.get("Итоговая сумма", 0)
    poter_ot_ofz = result_ofzpd.get("Итоговая сумма", 0)
    trabls_home = result_home.get("Общие плюс бабки", 0)
    pereplata_po_creditu_in_month = sum(v for k, v in result_credit.items() if k.startswith("Выплата по кредиту"))
    doxod_ot_vclada_in_month = sum(v for k, v in result_vclad.items() if k.startswith("Выплата по вкладу"))
    poter_ot_ofz_in_month = sum(v for k, v in result_ofzpd.items() if k.startswith("Выплата по офз"))

    full_credit = result_credit.get("Тело кредита", 0)

    # ФИКС 5: Передаем procent=inf_procent (как объявлено в классе Inflyaciya)
    infl = Inflyaciya(
        procent=inf_procent, 
        time=time
        )
        
    if infl.time > 0:
        i = inf_procent / 100
        total_credit = full_credit + pereplata_po_creditu
        poteri_vclada = doxod_ot_vclada - doxod_ot_vclada / ((1 + i) ** time)
        poteri_credit = total_credit - total_credit / ((1 + i) ** time)
        poteri_ot_ofz = poter_ot_ofz - poter_ot_ofz / ((1 + i) ** time)
        poteri_home = trabls_home - trabls_home / ((1 + i) ** time)
        month_discount = 1 - 1 / ((1 + i) ** (1 / 12))
        poteri_in_month_credita = pereplata_po_creditu_in_month * month_discount
        poteri_in_month_vclada = doxod_ot_vclada_in_month * month_discount
        poteri_ot_ofz_in_month = poter_ot_ofz_in_month * month_discount
        return {
            "Потери по вкладу от инфляции": round(poteri_vclada, 2),
            "Реальная переплата по кредиту (с учетом инфляции)": round(poteri_credit, 2),
            "Потеря от офз": round(poteri_ot_ofz, 2),
            "Потеря от дома": round(poteri_home, 2)
                }, {
                    "Потери по вкладу от инфляции в месяц": poteri_in_month_vclada,
                    "Потери кредита от инфляции в месяц": poteri_in_month_credita,
                    "Потери по офз от инфляции в месяц": poteri_ot_ofz_in_month
                    }
    return {}, {}


app = FastAPI(
    title = "Финансовый калькулятор",
    description=(
        "Кредиты, вклады, офзпд, недвижимость и учёт инфляции"
    ),
    version = "1.0.0",
)


@app.post("/credit",
          tags = ["Кредит"],
          summary = "Ануентный кредит"
          )
async def credit_endpoint(req: logica_1):
    try:
        return logica_1(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))



@app.post("/vclad",
          tags = ["Вклад"],
          summary = "Вклад"
          )
async def vclad_endpoint(req: logica_2):
    try:
        return logica_2(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))



@app.post("/ofzpd",
          response_model = OFZPD,
          tags = ["ОФЗ"],
          summary = "ОФЗ"
          )
async def ofzpd_endpoint(req: logica_3):
    try:
        return logica_3(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/home",
          response_model = Home,
          tags = ["Дом"],
          summary = "Дом"
          )
async def home_endpoint(req: logica_4):
    try:
        return logica_4(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))




@app.post("/inflyaciya",
          tags = ["Инфляция"],
          summary = "Инфляция"
          )
async def inflyaciya_endpoint(data: Inflyaciya):
    try:
        return obescenivanie()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))



@app.get("/health", tags=["Служебное"], summary="Проверка живости")
async def health():
    return {"status": "ok"}


'''   
def whater_you_need():
    messege = str(input("Какие вычисления вас интересуют: "))
    res_credit = {}
    res_vclad = {}
    res_ofzpd = {}
    res_home = {}
    if messege == "credit":
        res_credit = logica_1()
        infl = obescenivanie(
                              result_credit=res_credit,
                              result_vclad=res_vclad,
                              result_ofzpd=res_ofzpd
                              )
        return res_credit, infl
    elif messege == "vclad":
        res_vclad = logica_2()
        infl = obescenivanie(
                              result_credit=res_credit,
                              result_vclad=res_vclad,
                              result_ofzpd=res_ofzpd
                              )
        return res_vclad, infl
    elif messege == "ofzpd":
        res_ofzpd = logica_3()
        infl = obescenivanie(
                              result_credit=res_credit,
                              result_vclad=res_vclad,
                              result_ofzpd=res_ofzpd
                              )
        return res_ofzpd, infl
    elif messege == "home":
        res_home = logica_4()
        infl = obescenivanie(
                              result_credit=res_credit,
                              result_vclad=res_vclad,
                              result_ofzpd=res_ofzpd
                              )
        return res_home, infl
    elif messege == "over":
        res_credit = logica_1()
        res_vclad = logica_2()
        res_ofzpd = logica_3()
        infl = obescenivanie(
                              result_credit=res_credit,
                              result_vclad=res_vclad,
                              result_ofzpd=res_ofzpd
                              )
        return res_credit, res_vclad, res_ofzpd, infl

print(whater_you_need())
'''


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)