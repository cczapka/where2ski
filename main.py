from bs4 import BeautifulSoup
import requests

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


def get_forecast(resort, day):

	print("getting weather for", resort)

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

resorts = ['scheffau', 'kitzbuehel-kirchberg', 'nauders', 'serfaus-fiss-ladis', 'silvretta-arena-ischgl-samnaun', 'seefeld-rosshuette', 'wettersteinbahnen-ehrwald', 'stubaier-gletscher', 'hintertux', 'innsbruck-igls-patscherkofel', 'hochfuegen', 'zell-am-ziller', 'matrei', 'waidring-steinplatte']
forecasts = []

day_array = [0,1,2,3,4,5,6,7,8]
print(day_array)

forecast = get_forecast('scheffau', 0)
#display_full_forecast(resorts[0], day_array)

for resort in resorts:
	forecasts.append(get_forecast(resort, 7))

for f in forecasts:
	print(get_sun_raw(f),f.resort)
	#print (int(f.sun.strip('h')))


#forecasts_sorted = sorted(forecasts, key=get_sun_raw(fo))


forecasts.sort(key=get_sun_raw, reverse=True)

print("-------------")

for f in forecasts:
	print(get_sun_raw(f),f.resort)
	#print (int(f.sun.strip('h')))

#wichtig wären noch
#