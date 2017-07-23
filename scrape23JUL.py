import arcpy
from time import time
import re
import requests
from copy import copy
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
arcpy.env.workspace = 'C:\workingDirectory'
csv = 'datafile.txt'

class MultipleResults(Exception):
	pass

def writeCSV(rowlist, csv):
	print rowlist
	try:
		file = open(csv, "a")
	except IOError:
		print 'The text file is locked. Please close it and try again.'
		sys.exit(1)
	for item in rowlist:
		item = item.replace(",", "")
		item = item.replace("$", "")
		#item = item.replace(u'\xa0', u'Null')#I had considered wanting nulls recorded explicitly
		try:
			file.write(item.encode('utf-8') + ", ")
		except UnicodeEncodeError:
			file.write("UnicodeError, ")
	file.write('\n')
	file.close()
	

	


t = time()

connect = requests.get('https://www.google.com')
connect.raise_for_status()
#check for internet connection, additionally python will need permission to access internet

browser = webdriver.PhantomJS('C:\Program Files\phantomjs') #phantomJS is a headless browser allowing for scraping without rendering the pages.
#appropriate driver must be in PATH e.g. geckodriver for FF

browser.get('http://okanoganwa.taxsifter.com/Search/Results.aspx')#I started with the Okanogan Assessor site
iAgree = browser.find_element_by_name('ctl00$cphContent$btnAgree')
iAgree.click() #click user agreement, an alternative would be to request the cookie with driver.manage().getCookies()

wait = WebDriverWait(browser, 2)
wait.until(EC.presence_of_element_located((By.ID, 'q')))
#waiting allows for dynamic pages to finish loading. Here it is waiting for the presence of the search tool (ID: 'q')

fc = "2017-07-10_Landuse.shp"
#Im reading the parcel ID numbers from an ESRI .shp I downloaded from Okanogan FTP site
fields = ('ASSESSOR', 'scrape')#the fields to read/write in the .shp, I added [scrape], [Assessor] has the parcel IDs
vals = []#this list grows as parcelIDs are found that are invalid, useful when codes that aren't actually ID's are used, e.g. 'R/W'

#total = int(arcpy.GetCount_management(fc).getOutput(0))
i = -1
#iterate to count progress
with arcpy.da.UpdateCursor(fc, fields) as cursor:
	for row in cursor:
		rowlist = []
		p = str(row[0])
		print vals
		try:
			if row[1] == '' and row[0] not in vals:
				url = ('http://okanoganwa.taxsifter.com/Search/results.aspx?q=' + p)
				
				#test urls:
				#url = ('http://okanoganwa.taxsifter.com/Search/results.aspx?q=0000000000')#bad parcel id
				#url = ('http://okanoganwa.taxsifter.com/Search/results.aspx?q=US')#yield multiple records
				#url = ('http://okanoganwa.taxsifter.com/Search/results.aspx?q=3527051004')#multi building, foundation - null
				#url = ('http://okanoganwa.taxsifter.com/Search/results.aspx?q=1250110000')#multi building, no foundation
				#url = ('http://okanoganwa.taxsifter.com/Search/results.aspx?q=4026293006')#single building, foundation - null
				#url = ('http://okanoganwa.taxsifter.com/Search/results.aspx?q=4026303003')#land only
				#url = ('http://okanoganwa.taxsifter.com/Search/results.aspx?q=4026292009')#improvements only - this case could be improved by finding info on the misc improvements
				#url = ('http://okanoganwa.taxsifter.com/Search/results.aspx?q=7471180000')#single building, foundation - concrete
				#url = ('http://okanoganwa.taxsifter.com/Search/results.aspx?q=9940270532')#UnicodeError
				
				elapsed = int(abs(time() - t))
				m, s = divmod(elapsed, 60)
				h, m = divmod(m, 60)
				e = "%d:%02d:%02d" % (h, m, s)
				i += 1
				print 'Collected ', i, 'parcels.', e, ' elapsed.'
				#prints number of searches and time elapsed
				
				browser.get(url)
				print 'Getting ' + url
				#fetches webpage
				
				wait.until(EC.presence_of_element_located((By.LINK_TEXT, 'Assessor')))
				#wait for page to load
				html = browser.page_source 
				soup = BeautifulSoup(html, 'html.parser')
				
				if soup.find(id='ctl00_cphContent_Repeater1_ctl01_pnlResult'):
					raise MultipleResults
					#if the search results in multiple properties throws an error
				assessor = browser.find_element_by_link_text('Assessor')
				assessor.click()
				print 'Getting ' + url + ' assessor page'
				#click to get to assessor page
				
				#assessor page
				wait.until(EC.presence_of_element_located((By.LINK_TEXT, 'Assessor')))
				#wait until table loads
				html = browser.page_source 
				soup = BeautifulSoup(html, 'html.parser')
				
				parcel = soup.find(id="ctl00_cphContent_ParcelOwnerInfo1_lbParcelNumber").string
				rowlist.append(parcel) 
				#confirm which ID is being collected
				revenueCode = soup.find(id="ctl00_cphContent_ParcelOwnerInfo1_lbMID1Value").string
				rowlist.append(revenueCode) 
				#Dept of Revenue land use codes
				if soup.find(text="Improvements:"):
					improvement = soup.find(text="Improvements:").findNext('td').contents[0]
					rowlist.append(improvement)  
					#assessed improvement value (excludes land value)
				
					appraisal = browser.find_element_by_link_text('Appraisal')
					appraisal.click()
					
					wait.until(EC.presence_of_element_located((By.LINK_TEXT, 'Assessor')))
					html = browser.page_source  
					soup = BeautifulSoup(html, 'html.parser')
					text = re.compile('Year Built')
					#on the TaxSifter site there are extra spaces around 'Year Built'
					#this ignores the extra spaces.
					k = 0
					#for parcels with multiple buildings the code will iterate
					if soup.findAll(text=text):
						for th in soup.findAll(text=text):
							thParent = th.parent
							tr = th.find_parent('tr')
							index = tr.index(thParent)
							td2 = tr.find_next_sibling('tr')
							tdString = td2.contents[index].string.strip()
							clsString = td2.find_parent('td').find('div', class_="subHeader").string.strip()
							k += 1
							rowlist1 = copy(rowlist)
							rowlist1.append('building' + str(k))
							rowlist1.append(tdString)
							rowlist1.append(clsString)
							
							
							#search for a foundation row & value
							try:
								thString = th.find_parents('tbody')[1].find(text='Foundation').findNext('td').text
								rowlist1.append(thString)
								writeCSV(rowlist1, csv)
								row[1] = 'all'
								cursor.updateRow(row)
								#complete set
							except AttributeError:
								row[1] = 'noFound'
								cursor.updateRow(row)
								rowlist1.append('Null')
								writeCSV(rowlist1, csv)
								#escapes with parcelID, landuse code, improvement value & year built
					
					else:
						row[1] = 'noYrBlt'
						cursor.updateRow(row)
						writeCSV(rowlist, csv)
						#escapes with parcelID, landuse code & improvement value
				else:
					row[1] = 'noImp'
					cursor.updateRow(row)
					writeCSV(rowlist, csv)
					#escapes with parcelID, landuse code & improvement value
			
		except TimeoutException:
			row[1] = 'TimeoutEx'
			cursor.updateRow(row)
			vals.append(p)
			rowlist.append(p)
			rowlist.append('Timeout Exception')
			writeCSV(rowlist, csv)
			print 'Timeout Exception'
		except MultipleResults:
			row[1] = 'multiResults'
			cursor.updateRow(row)
			vals.append(p)
			rowlist.append(p)
			rowlist.append('Multiple results')
			writeCSV(rowlist, csv)
			print 'Multiple results'