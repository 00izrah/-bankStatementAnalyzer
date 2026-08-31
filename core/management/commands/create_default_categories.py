from django.core.management.base import BaseCommand
from core.models import Category


class Command(BaseCommand):
    help = 'Creates or updates default Nigerian banking system categories'

    def handle(self, *args, **kwargs):
        default_categories = [
            {
                'name': 'Bank Charges & Fees',
                'description': 'EMTL levy, stamp duty, SMS alert charges, card maintenance, and bank VAT',
                'keywords': 'bank charges,emtl,levy,stamp duty,sms alert,sms charge,alert charge,card maintenance,maintenance fee,acct maint,account maintenance,ussd session,ussd,vat on sms,vat charge,bank charge,token fee,commission,interest charge,overdraft fee',
            },
            {
                'name': 'Airtime & Data',
                'description': 'Mobile airtime, data bundles, and VTU top-ups (MTN, Airtel, Glo, 9mobile)',
                'keywords': 'airtime,data,vtu,data bundle,data sub,topup,top-up,recharge,mtn,airtel,glo,9mobile,etisalat,globacom',
            },
            {
                'name': 'Utilities',
                'description': 'Electricity bills (IKEDC, EKEDC, AEDC, etc.), cable TV (DStv, GOtv, StarTimes), water, and internet',
                'keywords': 'utilities,utility,electricity,power,light,nepa,ikedc,ekedc,aedc,eedc,ibedc,phedc,kedco,buypower,irecharge,dstv,gotv,showmax,startimes,multichoice,spectranet,smile,ipnx,fiber,water bill,waste,refuse',
            },
            {
                'name': 'Food & Dining',
                'description': 'Restaurants, fast food, groceries, meals, snacks, food delivery, and supermarkets',
                'keywords': 'food,dining,lunch,dinner,breakfast,meal,meals,shawarma,snack,snacks,drinks,groceries,grocery,supermarket,market,foodstuff,meat,fish,rice,bread,suya,soup,cook,cooking,chef,chowdeck,glovo,eden life,chicken republic,the place,theplace,kilimanjaro,mega chicken,dominos,pizza,kfc,sweet sensation,cold stone,restaurant,cafe,eatery,bakery,foodcourt,shoprite,spar,ebeano,hubmart,justrite',
            },
            {
                'name': 'Transportation',
                'description': 'Ride-hailing (Uber, Bolt, inDrive), petrol/fuel stations, flights, and vehicle maintenance',
                'keywords': 'transport,transportation,fare,ride,uber,bolt,taxify,indrive,taxi,cab,fuel,petrol,diesel,gas,oil,totalenergies,nnpc,mobil,conoil,ardova,oando,flight,airline,air peace,ibom air,bus,brt,garage,auto,car repair,car wash,mechanic',
            },
            {
                'name': 'Betting & Entertainment',
                'description': 'Sports betting, gaming, streaming services, cinema, and concerts',
                'keywords': 'entertainment,betting,bet9ja,sportybet,1xbet,betway,msport,paripesa,nairabet,cinema,filmhouse,silverbird,movie,movies,netflix,spotify,apple.com,youtube premium,game,gaming,playstation,ticket,concert,club,lounge,outing',
            },
            {
                'name': 'Savings & Investments',
                'description': 'Fintech savings apps, mutual funds, stock investments, and crypto',
                'keywords': 'savings,invest,investment,investments,cowrywise,piggyvest,bamboo,chaka,risevest,trove,shares,stock,mutual fund,crypto,binance,bybit,ajo,esusu,contribution,thrift',
            },
            {
                'name': 'Shopping',
                'description': 'Retail purchases, clothing, shoes, fashion, electronics, gadgets, and e-commerce',
                'keywords': 'shopping,shop,store,mall,clothes,clothing,shirt,trousers,dress,shoes,shoe,bag,bags,sneakers,thrift,okrika,boutique,fashion,accessories,wristwatch,gadget,phone,laptop,electronics,jumia,konga,amazon,aliexpress,paystack,flutterwave,moniepoint',
            },
            {
                'name': 'Healthcare',
                'description': 'Personal care, skincare, salon, hospitals, pharmacies, clinics, medical labs, and health insurance',
                'keywords': 'healthcare,health,personal care,skincare,skin care,care,hair,haircut,salon,barbing,barber,beauty,cosmetics,makeup,nails,spa,grooming,perfume,toiletries,soap,lotion,cream,hospital,clinic,pharmacy,chemist,medplus,healthplus,medical,doctor,lab,dental,dentist,optician,drugs,medicine,hmo,insurance',
            },
            {
                'name': 'Education',
                'description': 'School fees, university tuition, courses, books, and certifications',
                'keywords': 'education,school,college,university,tuition,fees,school fees,course,training,udemy,coursera,book,books,exam,waec,jamb,cert,certification,assignment,project',
            },
            {
                'name': 'Housing',
                'description': 'Rent, mortgage, estate service charge, and home repairs',
                'keywords': 'housing,rent,house,apartment,estate dues,service charge,mortgage,plumber,electrician,carpenter,home maintenance,repair,property,cleaner',
            },
            {
                'name': 'Transfers & P2P',
                'description': 'Peer-to-peer bank transfers, personal payments, and family support',
                'keywords': 'trf,transfer,transfers,nip,onebank,onebank transfer,fip,instant payment,send money,pocket money,allowance,family,gift,funds,support,flex,urgent 2k,urgent',
            },
            {
                'name': 'Income',
                'description': 'Salaries, freelance earnings, dividends, sales revenue, and business inflows',
                'keywords': 'income,salary,wages,payroll,allowance,stipend,dividend,interest,interest capitalization,inflow,credit,refund,reversal,cashback',
            },
            {
                'name': 'Other',
                'description': 'Uncategorized or miscellaneous transactions',
                'keywords': '',
            },
        ]

        created_count = 0
        updated_count = 0

        for cat_data in default_categories:
            cat, created = Category.objects.get_or_create(
                name=cat_data['name'],
                is_system=True,
                defaults={
                    'description': cat_data['description'],
                    'keywords': cat_data['keywords'],
                    'user': None,
                }
            )
            if not created:
                # Update keywords and description for existing system categories
                cat.description = cat_data['description']
                cat.keywords = cat_data['keywords']
                cat.save()
                updated_count += 1
            else:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Successfully seeded default categories ({created_count} created, {updated_count} updated)'
        ))