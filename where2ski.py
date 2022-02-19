from bs4 import BeautifulSoup
import requests
import datetime

class Forecast:
	def __init__(self, resort, day, date, tmin_m, tmax_m, snowcm_m, tmin_v, tmax_v, snowcm_v, rrp, rrr, sun, snowl, wind):
		self.resort=resort
		self.day=day
		self.date=date
		self.tmin_m=tmin_m
		self.tmax_m=tmax_m
		self.snowcm_m=snowcm_m
		self.tmin_v=tmin_v
		self.tmax_v=tmax_v
		self.snowcm_v=snowcm_v
		self.rrp=rrp
		self.rrr=rrr
		self.sun=sun
		self.snowl=snowl
		self.wind=wind


def menu():
	print()

def get_forecast(resort, day):

	print("... for", ((datetime.datetime.today()+datetime.timedelta(days=int(day))).strftime("%B %d, %Y")), resort)

	html_text = requests.get('https://www.bergfex.at/' + resort + '/wetter/prognose/').text
	soup = BeautifulSoup(html_text, 'lxml')


	weatherdays = soup.find(id=("forecast-day-"+str(day)))
	# print soup to debug and find corresponding tags etc.
	#print(weatherdays.prettify())


	#groups = weatherdays.find_all('div', {'class':'group'})
	#for group in groups:
	#	print("Group-------\n:",group.text)

	date = weatherdays.find(class_="date").text
	# work with a list since mountain and valley attributes are not distinguishable
	tmins = weatherdays.find_all('div',{'class':'tmin'})
	tmin_m = tmins[0].text
	tmin_v = tmins[1].text
	tmaxs = weatherdays.find_all('div',{'class':'tmax'})
	tmax_m = tmaxs[0].text
	tmax_v = tmaxs[1].text
	snowcms = weatherdays.find_all('div',{'class':'nschnee'})
	snowcm_m = snowcms[0].text.strip()
	snowcm_v = snowcms[1].text.strip()

	rrp = weatherdays.find(class_="rrp").text.strip()
	rrr = weatherdays.find(class_="rrr").text.strip()
	sun = weatherdays.find(class_="sonne").text.strip()
	snowl = weatherdays.find(class_="sgrenze").text.strip()
	wind = weatherdays.find(class_="ff").text.strip()

	return Forecast(resort, day, date, tmin_m, tmax_m, snowcm_m, tmin_v, tmax_v, snowcm_v, rrp, rrr, sun, snowl, wind)


def display_day_forecast(fc):
	print(f'''
	{fc.date}

	Mountain:	{fc.tmin_m},	{fc.tmax_m},	{fc.snowcm_m}
	Valley:		{fc.tmin_v},	{fc.tmax_v},	{fc.snowcm_v}

	Humidity:	{fc.rrp}
	Precipitation:	{fc.rrr}
	Sun-hours:	{fc.sun}
	Snowline:	{fc.snowl}
	Wind:		{fc.wind}
	''')
		
	#test = soup.find("div", class_ = "touch-scroll-x")
	#print(test.prettify())

def display_full_forecast(resort, day_array):
	for day in day_array:
		display_day_forecast(get_forecast(resort, day))

def get_sun_raw(fc):
	return(fc.sun.strip('h'))



## Initialization

# add or remove resorts if necessary
resorts = ['scheffau', 'kitzbuehel-kirchberg', 'nauders', 'serfaus-fiss-ladis', 'silvretta-arena-ischgl-samnaun', 'seefeld-rosshuette', 'wettersteinbahnen-ehrwald', 'stubaier-gletscher', 'hintertux', 'innsbruck-igls-patscherkofel', 'hochfuegen', 'zell-am-ziller', 'matrei', 'waidring-steinplatte']
#resorts = ['scheffau', 'kitzbuehel-kirchberg', 'nauders', 'serfaus-fiss-ladis']
forecasts = []

# range based on the 9-day forecast of bergfex
day_array = ['0','1','2','3','4','5','6','7','8']

## Programflow start

day = input("\n!!MOIN!!\n\nWhich day from now do you wanna go skiing? Please enter a number between 0 (today) and 8: ")

while day not in day_array:
	day = input("\nWrong input. Please select a day in range 0 and 8: ")


#forecast = get_forecast('scheffau', 0)
#display_full_forecast(resorts[0], day_array)

# get weather data for each resort
print("\nGrabbing latest forecasts data...")
for resort in resorts:
	forecasts.append(get_forecast(resort, 7))

# only for debug
#for f in forecasts:
#	print(get_sun_raw(f),"h in",f.resort)

# sort resort-forecasts by sun hours
forecasts.sort(key=get_sun_raw, reverse=True)

print("------------------------------------------------------")
print("For", ((datetime.datetime.today()+datetime.timedelta(days=int(day))).strftime("%B %d, %Y")), "you can expect the following amount of sun hours for each of the resorts:")
for index, item in enumerate(forecasts):
	print("%i)	" %(index+1), get_sun_raw(item), "h in", item.resort)
	#print (int(f.sun.strip('h')))
print("------------------------------------------------------")

option = int(input("Please select a resort number to view more detailed information. Press 0 to quit: "))
while option != 0:
	if option > 0 and option <= len(forecasts):
		print("Showing detailed weather of", forecasts[option-1].resort)
		display_day_forecast(forecasts[option-1])
		option = int(input("Select other resort or press 0 to quit: "))
	else:
		option = int(input("Invalid option. Please select again: "))