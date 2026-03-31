"""
示例车型实例工厂
================
提供工厂函数创建示例 CarModel 实例。
每个工厂函数对应一款具体车型，属性值来源于标准车型库。
"""

from ontology_engine.core.ontology_registry import get_onto
from ontology_engine.config.enums import (
    BodyType, CarSizeLevel, PowerType, PriceBand, BrandCamp,
)


def create_byd_han():
    """比亚迪汉 EV — 纯电动轿车，20-30万，自主品牌"""
    onto = get_onto()
    with onto:
        car = onto.CarModel("比亚迪汉")
        car.power_type     = PowerType.PURE_EV.value
        car.body_type      = BodyType.SEDAN.value
        car.car_price_band = PriceBand.W20_30.value
        car.msrp           = 209800.0
        car.car_size_level = CarSizeLevel.MID.value
        car.brand_camp     = BrandCamp.DOMESTIC.value
    return car


def create_toyota_highlander():
    """丰田汉兰达 — 传统燃油 SUV，30-50万，合资品牌"""
    onto = get_onto()
    with onto:
        car = onto.CarModel("丰田汉兰达")
        car.power_type     = PowerType.FUEL.value
        car.body_type      = BodyType.SUV.value
        car.car_price_band = PriceBand.W30_50.value
        car.msrp           = 328800.0
        car.car_size_level = CarSizeLevel.MID_LARGE.value
        car.brand_camp     = BrandCamp.JOINT_VENTURE.value
    return car


def create_lixiang_l9():
    """理想 L9 — 增程式大型 SUV，30-50万，造车新势力"""
    onto = get_onto()
    with onto:
        car = onto.CarModel("理想L9")
        car.power_type     = PowerType.EREV.value
        car.body_type      = BodyType.SUV.value
        car.car_price_band = PriceBand.W30_50.value
        car.msrp           = 459800.0
        car.car_size_level = CarSizeLevel.LARGE.value
        car.brand_camp     = BrandCamp.NEW_FORCE.value
    return car


def create_audi_q2l():
    """奥迪 Q2L — 传统燃油小型 SUV，20-30万，传统豪华品牌"""
    onto = get_onto()
    with onto:
        car = onto.CarModel("奥迪Q2L")
        car.power_type     = PowerType.FUEL.value
        car.body_type      = BodyType.SUV.value
        car.car_price_band = PriceBand.W20_30.value
        car.msrp           = 229800.0
        car.car_size_level = CarSizeLevel.MINI.value
        car.brand_camp     = BrandCamp.LUXURY_TRAD.value
    return car
