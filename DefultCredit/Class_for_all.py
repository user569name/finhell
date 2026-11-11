from pydantic import BaseModel

class Credit(BaseModel):
    money_for_new_home: float
    vznos: float
    procent_for_credit: float
    time: float
class Vclad(BaseModel):
    time: float
    nach_vlozhenie: float
    procent_for_vclad: float
    dodep: float
    step: int
class OFZPD(BaseModel):
    time: float
    procent_ofz: float
    step_ofz: float
    money_for_ofz: float