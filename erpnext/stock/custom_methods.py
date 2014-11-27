from __future__ import unicode_literals
import frappe
import frappe.defaults

from frappe.utils import cstr, cint, flt, comma_or, nowdate

from frappe import _ ,msgprint
from erpnext.stock.utils import get_incoming_rate
from erpnext.stock.stock_ledger import get_previous_sle
from erpnext.controllers.queries import get_match_cond



#Check weather SUM of qty in all serials is equal to qty of item specified 
def validate_serial_qty(doc,method):
	for d in doc.get('mtn_details'):
		if doc.purpose in ['Manufacture','Repack']:
			if d.custom_serial_no and not d.target_batch and not d.qty_per_drum_bag and d.t_warehouse:
				sr_no=(d.custom_serial_no).splitlines()
				sr=''
				for s in sr_no:
					if sr:
						sr+=','+'\''+s+'\''
					else:
						sr='\''+s+'\'' 
				qty=frappe.db.sql("""select SUM(qty) from `tabSerial No` 
					where name in (%s)"""%(sr),as_list=1)
				if not d.qty==qty[0][0]:
					frappe.throw(_("Row {0} : Quantity in Serial No {1} must equal to Quantity for Item {2}").format(d.idx,d.custom_serial_no,d.item_code))

#Check weather Quality Checking is done for serials in serials field
def validate_serial_qc(doc,method):
	for d in doc.get('mtn_details'):
		if doc.purpose in ['Manufacture','Repack'] and d.s_warehouse:
			qc_req=frappe.db.get_value('Item',{"item_code":d.item_code},'inspection_required')
			ca_req=frappe.db.get_value('Item',{"item_code":d.item_code},'chemical_analysis')
			psd_req=frappe.db.get_value('Item',{"item_code":d.item_code},'psd_analysis')
			sa_req=frappe.db.get_value('Item',{"item_code":d.item_code},'ssa')
			if d.custom_serial_no:
				sr_no=(d.custom_serial_no).splitlines() or (d.custom_serial_no).split('\n')
				for sr in sr_no:
					check_qc_done(ca_req,sa_req,psd_req,sr,d.item_code)

def check_qc_done(qc,sa,psd,sr,item_code):
	qc_status=frappe.db.get_value('Serial No',{"item_code":item_code,"name":sr},'qc_status')
	sa_status=frappe.db.get_value('Serial No',{"item_code":item_code,"name":sr},'sa_analysis')
	psd_status=frappe.db.get_value('Serial No',{"item_code":item_code,"name":sr},'psd_status')
	if qc=='Yes' and qc_status=='':
		frappe.throw(_("QC Required for Serial {0} ").format(sr))
	elif sa=='Yes' and sa_status=='':
		frappe.throw(_("Surface Anaysis Required for Serial {0} ").format(sr))
	elif psd=='Yes' and psd_status=='':
		frappe.throw(_("PSD Anaysis Required for Serial {0} ").format(sr))
		


#check if there is serial no and is valid serial no
def validate_serial_no(d):

	if not d.custom_serial_no and frappe.db.get_value('Item',d.item_code,'serial_no')=='Yes':
		frappe.throw(_("Row {0}: Enter serial no for Item {1}").format(d.idx,d.item_code))
	elif d.custom_serial_no:
		sr_no=(d.custom_serial_no).splitlines() or (d.custom_serial_no).split('\n')
		for s in sr_no:
			if not frappe.db.get_value('Serial No',s,'name'):
				frappe.throw(_("Row {0}: Serial no {1} does not exist").format(d.idx,s))
			elif not frappe.db.get_value('Serial No',s,'item_code')==d.item_code:
				frappe.throw(_("Row {0}: Please select the Serial No regarding to Item Code {1}").format(d.idx,d.item_code))

#Check whether serial no specified delivery note
def validate_serial_no_dn(doc,method):
	for d in doc.get('delivery_note_details'):
		if not d.custom_serial_no:
			if frappe.db.get_value('Item',d.item_code,'serial_no')=='Yes':
				frappe.throw(_("Please select serial no at row {0}").format(d.idx))


#Check valid serial delivery note
def validate_serial_no_qty(doc,method): 
	sum_qty=0.0
	sr=[]
	for d in doc.get('delivery_note_details'):
		if frappe.db.get_value('Item',d.item_code,'serial_no')=='Yes' and d.custom_serial_no:
			serial_no=(d.custom_serial_no).splitlines() or (d.custom_serial_no).split('\n')
			for sr_no in serial_no:
				qty=frappe.db.get_value("Serial No",{'name':sr_no,'qc_status':'Accepted','status':'Available','item_code':d.item_code,'serial_no_warehouse':d.warehouse},'qty')
				if qty:
					sum_qty=flt(sum_qty)+flt(qty)
				else:
					frappe.throw(_("Please select valid serial no at row {0}").format(d.idx))
				sr.append(sr_no)
			if flt(d.qty) > flt(sum_qty):
				frappe.throw(_("Negative stock error:  {0} qty available in serial no {1}").format((flt(sum_qty)-flt(d.qty)),','.join(sr)))

#Check Whether QC done delivery note
def validate_qc_status(doc,method):
	for d in doc.get('delivery_note_details'):
		if d.custom_serial_no:#change it to custom_serial_no
			sr_n=(d.custom_serial_no).splitlines()
			for sr in sr_n:
				ca_req=frappe.db.get_value('Item',{"item_code":d.item_code},'chemical_analysis')
				psd_req=frappe.db.get_value('Item',{"item_code":d.item_code},'psd_analysis')
				sa_req=frappe.db.get_value('Item',{"item_code":d.item_code},'ssa')
				qc_status=frappe.db.get_value('Serial No',{"item_code":d.item_code,"name":sr},'qc_status')
				sa_status=frappe.db.get_value('Serial No',{"item_code":d.item_code,"name":sr},'sa_analysis')
				psd_status=frappe.db.get_value('Serial No',{"item_code":d.item_code,"name":sr},'psd_status')
				if ca_req=='Yes' and qc_status!='Accepted':
					frappe.throw(_("QC Not Accpeted for Serial {0} ").format(sr))
				elif psd_req=='Yes' and psd_status!='Accepted':
					frappe.throw(_("PSD Anaysis Not Accpeted for Serial {0} ").format(sr))
				elif sa_req=='Yes' and sa_status!='Accepted':
					frappe.throw(_("SA Anaysis Not Accpeted for Serial {0} ").format(sr))

def update_serial_no(doc,method): #Rohit_sw
	for d in doc.get('delivery_note_details'):
		if d.custom_serial_no:
			serial_no=(d.custom_serial_no).splitlines()
			qty=cstr(d.qty)
			for sr_no in serial_no:
				if cint(qty) > 0:
					qty=flt(qty) - flt(frappe.db.get_value('Serial No',sr_no,'qty'))
					make_serialgl_dn(d,sr_no,frappe.db.get_value('Serial No',sr_no,'qty'),doc)
					frappe.db.sql("update `tabSerial No` set qty=0.0,status='Delivered' where name='%s'"%(sr_no))
					if (cint(0)-cint(qty))>0:
						amend_serial_no(d,sr_no,qty)


def make_serialgl_dn(d,serial_no,qty,doc):
	bi=frappe.new_doc('Serial Stock')
	bi.document=doc.name
	bi.item_code=d.item_code
	bi.serial_no=serial_no
	bi.qty=cstr(qty)
	bi.warehouse=d.warehouse
	bi.parent=serial_no
	bi.parentfield='serial_stock'
	bi.parenttype='Serial No'
	bi.save(ignore_permissions=True)

def amend_serial_no(d,serial_no,qty):
	sr_no=frappe.new_doc("Serial No")
	amend_qty=cint(frappe.db.get_value('Serial No',serial_no,'amend_qty')) or 0 + 1
	sr_no.serial_no=serial_no.split('-')[0] + '-' + cstr(amend_qty)
	sr_no.amend_qty=amend_qty
	sr_no.make_from=serial_no
	sr_no.status="Available"
	sr_no.item_code=d.item_code
	sr_no.item_name=d.item_name
	sr_no.qty=cstr(flt(0.0)-flt(qty))
	sr_no.serial_no_warehouse=d.warehouse
	sr_no.item_group=d.item_group
	sr_no.decription=d.description
	sr_no.qc_status='Accepted'
	sr_no.save(ignore_permissions=True)


def update_serialgl_dn(doc,method):
	qty=0
	for d in doc.get('delivery_note_details'):
		if d.custom_serial_no:
			serial_no=(d.custom_serial_no).splitlines()
			for sr_no in serial_no:
				serial_no_qty=frappe.db.sql("select ifnull(qty,0) from `tabSerial Stock` where parent='%s' and document='%s'"%(sr_no,doc.name),as_list=1)
			        if serial_no_qty:
					qty=qty+cint(serial_no_qty[0][0])
				amend_qty=frappe.db.get_value('Serial No',{'make_from':sr_no},'qty') or 0
				qty = qty + amend_qty
				frappe.db.sql("update `tabSerial No` set qty=%s,status='Available' where name='%s'"%(qty,sr_no))
				frappe.db.sql("delete from `tabSerial Stock` where parent='%s' and document='%s'"%(sr_no,doc.name))
				frappe.db.sql("delete from `tabSerial No` where make_from='%s'"%(sr_no))


#Function to handle serials
def generate_serial_no_fg(doc,method):
	previous_source_batch=''
	#source_batch_no=''
	for d in doc.get('mtn_details'):
		if doc.purpose in ['Manufacture','Repack','Material Receipt']:
			
			if d.t_warehouse and d.qty_per_drum_bag:
				generate_serial_no_per_drum(d,doc)
			
			elif d.t_warehouse and not d.qty_per_drum_bag:
				generate_serial_no_and_batch(d,previous_source_batch,doc)
				validate_serial_no(d)
			
			elif d.t_warehouse:
				validate_serial_no(d)

			if d.source_batch:
				previous_source_batch=d.source_batch
			

		elif doc.purpose in ['Material Issue','Purchase Return']:
			validate_serial_no(d)
			issue_serial_no(d,'Not Available',0)
		
		elif doc.purpose in ['Sales Return']:
			validate_serial_no(d)

		elif doc.purpose in ['Material Transfer']:
			validate_serial_no(d)
			qty=validate_qty_in_serial(d)
			update_serial_no_warehouse_qty(qty,d,doc)

		if d.t_warehouse and d.target_batch and doc.purpose in ['Manufacture','Repack']:
			update_batch_status("Yes",d.target_batch)

def update_serial_no_warehouse_qty(qty,d,doc):
	sr_no=(d.custom_serial_no).splitlines()
	qty_temp=cint(d.qty)
	for sr in sr_no:
		serial_qty=frappe.db.get_value("Serial No",sr,"qty")
		if qty_temp > cint(serial_qty):
			sn=frappe.get_doc("Serial No",sr)
			sn.update({"serial_no_warehouse":d.t_warehouse})
			sn.save(ignore_permissions=True)
			qty_temp -= cint(serial_qty)

		elif qty_temp < cint(serial_qty):
			sn=frappe.get_doc("Serial No",sr)
			sn.update({"qty":qty_temp,"serial_no_warehouse":d.t_warehouse})
			sn.save(ignore_permissions=True)
			rem_qty=cint(serial_qty)-qty_temp
			amend_serial_no_mt(sr,rem_qty,serial_qty,sn.name,d,qty_temp,doc)

def update_serial_no_mt_cancel(doc,method):
	for d in doc.get('mtn_details'):
		if d.custom_serial_no and doc.purpose=='Material Transfer':
			serials=get_serials_from_field(d)
			update_amended_serials(serials,doc,d)

def update_amended_serials(serials,doc,d):
	for sn in serials:
		change_serial_details(sn,doc,d)

def change_serial_details(sn,doc,d):
	amended_qty=frappe.db.sql("""select qty,amended_serial_no from `tabSerial QTY Maintain` where parent='%s' and document='%s'"""%(sn,doc.name))
	srn=frappe.get_doc("Serial No",sn)
	if amended_qty:
		qty=srn.qty+flt(amended_qty[0][0])
	else:
		qty=srn.qty+0
	srn.update({"qty":qty,"serial_no_warehouse":d.s_warehouse})
	srn.save(ignore_permissions=True)
	if amended_qty:
		sr=frappe.get_doc("Serial No",amended_qty[0][1])
		qty=sr.qty-flt(amended_qty[0][0])
		sr.update({"qty":qty})
		sr.save(ignore_permissions=True)



def get_serials_from_field(d):
	serials=(d.custom_serial_no).splitlines()
	return serials


def amend_serial_no_mt(sr,rem_qty,serial_qty,name,d,qty_temp,doc):
	parent=(name).split('-') or name
	idx=frappe.db.sql("""select ifnull(max(idx),0) 
		from `tabSerial QTY Maintain` 
		where parent='%s'"""%(parent[0]),as_list=1)
	if idx:
		idx=idx[0][0]
	else:
		idx=0
	name=create_new_serial_no(idx,sr,rem_qty,d,parent[0])
	update_maintain_serial(name,sr,serial_qty,rem_qty,idx,doc,parent[0])

def create_new_serial_no(idx,sr,rem_qty,d,parent):
	sn=frappe.new_doc('Serial No')
	sn.serial_no=parent+'-'+cstr(idx+1)
	sn.serial_no_warehouse=d.s_warehouse
	sn.item_code=d.item_code
	sn.status='Available'
	sn.qty=rem_qty
	sn.finished_good='No'
	sn.save(ignore_permissions=True)
	return sn.name

def update_maintain_serial(name,sr,serial_qty,qty_temp,idx,doc,parent):
	sqm=frappe.new_doc("Serial QTY Maintain")
	sqm.amended_serial_no=name
	sqm.idx=cint(idx)+1
	sqm.qty=qty_temp
	sqm.document=doc.name
	sqm.parent_serial=parent
	sqm.parent=sr
	sqm.parenttype='Serial No'
	sqm.parentfield='serial_qty_maintain'
	sqm.save(ignore_permissions=True)



def validate_qty_in_serial(d):
	if d.custom_serial_no:
		serials=get_serials_list(d.custom_serial_no)
		qty=get_qty_for_serials(serials)
		if not d.qty <= qty:
			frappe.throw(_("Quantity Should be less than or Equal to {0}").format(qty))
		else:
			return qty

def get_serials_list(serials):
	sr_no=(serials).splitlines()
	sr=''
	for s in sr_no:
		if sr:
			sr+=','+'\''+s+'\''
		else:
			sr='\''+s+'\''
	return sr 

def get_qty_for_serials(serials):
	qty=frappe.db.sql("""select ifnull(SUM(qty),0) 
		from `tabSerial No` 
		where name in (%s) """%(serials),as_list=1)
	if qty:
		return qty[0][0]
	else:
		return 0

#Automatically generate serials based on qty and qty per drum
def generate_serial_no_per_drum(d,doc):
	series=frappe.db.get_value('Serial No',{'name':d.serial_no_link,'status':'Available','item_code':d.item_code},'naming_series')
	if series:
		validate_serial_no(d)
		serial_no = (d.custom_serial_no).splitlines()
		for sn in serial_no:
			if sn:
				frappe.db.sql("""update `tabSerial No` 
					set finished_good='Yes',qty='%s',serial_no_warehouse='%s' 
					where name='%s'"""%(d.qty_per_drum_bag, d.t_warehouse,sn))
		qty=cint(d.qty) - cint(d.qty_per_drum_bag)
		serial_no_name=d.serial_no_link + '\n'
		while cint(qty) > 0:
			qty_for_negative=cint(qty)
			qty = cint(qty) - cint(d.qty_per_drum_bag)
			if cint(qty) < 0:
				name=create_serial_no(d,series,qty_for_negative)
			else:
				name=create_serial_no(d,series,d.qty_per_drum_bag)
			serial_no_name+= name + '\n'
		d.custom_serial_no=serial_no_name
		frappe.db.sql("""update `tabStock Entry Detail` 
			set custom_serial_no='%s' 
			where parent='%s' 
			and item_code='%s'"""%(serial_no_name,doc.name,d.item_code))


#Create new serial no with current iten and make status available
def create_serial_no(d,series,qty):
	sr_no=frappe.new_doc('Serial No')
	sr_no.naming_series=series
	sr_no.item_code=d.item_code
	sr_no.qty=cstr(qty)
	sr_no.status="Available"
	sr_no.item_name=d.item_name
	sr_no.is_repacked='Yes'
	sr_no.serial_no_warehouse=d.t_warehouse
	sr_no.item_group=frappe.db.get_value("Item",{"item_code":d.item_code},'item_group')
	sr_no.description=d.description
	sr_no.finished_good='Yes'
	sr_no.save(ignore_permissions=True)
	return sr_no.name


#create target batch no based on series of source batch no
def create_target_batch(d,previous_source_batch):
	t_batch_no=get_batch_id(previous_source_batch)
	if t_batch_no:
		batch=frappe.new_doc('Batch')
		batch.batch_id=t_batch_no
		batch.item=d.item_code
		batch.warehouse=d.t_warehouse
		batch.creation='Auto'
		batch.save(ignore_permissions=True)
		d.target_batch=batch.name
	return d.target_batch

def get_batch_id(batch_no):
        import re
        batch_no=re.sub(r'\d+(?=[^\d]*$)', lambda m: str(int(m.group())+1).zfill(len(m.group())), batch_no)
        return batch_no

#Automatically generate batch and serial no on submission these serial no will be source serial in next process
def generate_serial_no_and_batch(d,previous_source_batch,doc):
	target_batch=d.target_batch#new anand
	if previous_source_batch:
		target_batch=create_target_batch(d,previous_source_batch)
	elif not previous_source_batch and not d.target_batch:
		validate_serial_no(d)
	sr_no=frappe.new_doc('Serial No')
	sr_no.serial_no=target_batch
	sr_no.item_code=d.item_code
	sr_no.qty=cstr(d.qty)
	sr_no.status="Available"
	sr_no.item_name=d.item_name
	sr_no.serial_no_warehouse=d.t_warehouse
	sr_no.item_group=frappe.db.get_value("Item",{"item_code":d.item_code},'item_group')
	sr_no.description=d.description
	sr_no.batch_no=d.target_batch
	sr_no.finished_good='Yes'
	sr_no.save(ignore_permissions=True)
	d.custom_serial_no=d.target_batch
	frappe.db.sql("update `tabStock Entry Detail` set custom_serial_no='%s' where parent='%s' and item_code='%s'"%(d.custom_serial_no,doc.name,d.item_code))



def issue_serial_no(d,status,qty):
		if d.custom_serial_no:
			sr_no=(d.custom_serial_no).splitlines() or (d.custom_serial_no).split('\n')
			for s in sr_no:
				frappe.db.sql(""" update `tabSerial No` set status='%s' and
					serial_no_warehouse='%s' and qty=%s where name='%s'
					"""%(status, d.s_warehouse or d.t_warehouse, cint(qty), s))
				

#Update Serial Warehouse in serial no on material transfer
def update_serial_no_warehouse(doc,method):
	if doc.purpose=='Material Transfer':
		for item in doc.get("mtn_details"):
			validate_serial_no(item)
			if item.custom_serial_no:
				sr_no=(item.custom_serial_no).splitlines()
				for sr in sr_no:
					frappe.db.sql("""update `tabSerial No` set serial_no_warehouse='%s' where name='%s'"""%(item.t_warehouse,sr))

#update qty to serial no on use
def update_qty(doc,method):
	for d in doc.get('mtn_details'):
		if d.s_warehouse and d.custom_serial_no and doc.purpose in ['Manufacture','Repack','Material Receipt']:
			sr_no=(d.custom_serial_no).split('\n')
			qty=cint(round(d.qty))
			for s in sr_no:
				if s:
					serial_qty=frappe.db.get_value('Serial No',s,'qty')
					if qty >= serial_qty:
						qty= cint(qty) - cint(serial_qty)
						frappe.db.sql("update `tabSerial No` set qty=qty-%s where name='%s'"%(cint(serial_qty),s))
						make_serialgl(d,s,serial_qty,doc)
					elif qty > 0:
						frappe.db.sql("update `tabSerial No` set qty=qty-%s where name='%s'"%((cint(qty)),s))
						make_serialgl(d,s,qty,doc)
						qty= cint(qty) - cint(serial_qty)

#keep track of serials used in stock entry
def make_serialgl(d,serial_no,qty,doc):
	#change Serial Maintain to Serial Stock
	bi=frappe.new_doc('Serial Stock')
	bi.document=doc.name
	bi.item_code=d.item_code
	bi.serial_no=serial_no
	bi.qty=cstr(qty)
	bi.warehouse=d.s_warehouse or d.t_warehouse
	bi.parent=serial_no
	bi.parentfield='serial_stock'
	bi.parenttype='Serial No'
	bi.save(ignore_permissions=True)


#Update Warehouse with serial
def update_serial_in_warehouse(doc,method):
	for d in doc.get('mtn_details'):
		if d.t_warehouse and d.custom_serial_no and frappe.db.get_value('Warehouse',d.t_warehouse,'is_flowbin')=='Yes':
			sr_no=(d.custom_serial_no).splitlines() or (d.custom_serial_no).split('\n')
			for s in sr_no:
				frappe.db.sql("""update tabWarehouse 
					set serial_no='%s' where name='%s'"""%(s,d.t_warehouse))


#get source serial grade and attach it to target serial
def update_target_serial_grade(doc,method):
	if doc.purpose in ['Manufacture','Repack']:
		grade=''
		for d in doc.get('mtn_details'):
			if d.s_warehouse and d.custom_serial_no:
				grade=d.grade
			elif d.t_warehouse and d.custom_serial_no:
				sr_no=(d.custom_serial_no).splitlines() or (d.custom_serial_no).split('\n')
				if sr_no:
					for sr in sr_no:
						frappe.db.sql("""update `tabSerial No` 
							set grade='%s' where name='%s'"""%(grade,sr))
					grade=''

#track of serials
def update_serialgl(doc,method):
	for d in doc.get('mtn_details'):
		if doc.purpose in ['Manufacture','Repack','Material Receipt']:
			if d.custom_serial_no and d.s_warehouse:
				serial_no=(d.custom_serial_no).split('\n')
				for sr_no in serial_no:
					qty=0
					#change Serial Maintain to Serial Stock
					serial_no_qty=frappe.db.sql("""select qty from `tabSerial Stock` 
						where parent='%s' and document='%s'"""%(sr_no,doc.name),as_list=1)
					if serial_no_qty:
						frappe.db.sql("""update `tabSerial No` 
							set qty=qty+%s,status='Available' 
							where name='%s'"""%(serial_no_qty[0][0],sr_no))
						#change Serial Maintain to Serial Stock
						frappe.db.sql("""delete from `tabSerial Stock` 
							where parent='%s' and document='%s'"""%(sr_no,doc.name))
			else:
				if d.custom_serial_no:
					serial_no=(d.custom_serial_no).split('\n')
					for sr_no in serial_no:
						frappe.db.sql("""delete from `tabSerial No` 
							where name='%s'"""%(sr_no))

#update batch status on use
def update_batch_status(status,target_batch):
	frappe.db.sql("""update `tabBatch` 
		set used='%s' where name='%s'"""%(status,target_batch))

def get_serial_no_dn(doctype,txt,searchfield,start,page_len,filters):
	doc=filters['doc']
	cond=get_conditions(doc)
	frappe.errprint(cond)
	if cond:
		return frappe.db.sql("""select name from `tabSerial No` %s and status='Available' and item_code='%s'"""%(cond,doc['item_code']),debug=1) or [['']]
	else:
		return [['']]

def get_conditions(doc):
	con=''
	qc=frappe.db.sql("""select chemical_analysis,psd_analysis,ssa from `tabItem` 
		where item_code='%s'"""%(doc['item_code']),as_list=1)
	if qc[0][0]=='Yes' and qc[0][1]=='Yes' and qc[0][2]=='Yes':
		con="where qc_status='Accepted' and sa_analysis='Accepted' and psd_status='Accepted'"
	elif qc[0][0]=='Yes' and qc[0][1]=='Yes':
		con="where qc_status='Accepted' and psd_status='Accepted'"
	elif qc[0][0]=='Yes' and qc[0][2]=='Yes':
		con="where qc_status='Accepted' and sa_analysis='Accepted'"
	elif qc[0][1]=='Yes' and qc[0][2]=='Yes':
		con="where sa_analysis='Accepted' and psd_status='Accepted'"
	elif qc[0][0]=='Yes':
		con="where qc_status='Accepted'"
	elif qc[0][1]=='Yes':
		con="where psd_status='Accepted'"
	elif qc[0][2]=='Yes':
		con="where sa_analysis='Accepted'"

	return con

#return query to get serials
def get_serial_no(doctype,txt,searchfield,start,page_len,filters):
	doc=filters['doc']
	if doc['t_warehouse'] and doc['purpose']=='Manufacture' or doc['purpose']=='Repack' and doc['qty_per_drum_bag']:
		return frappe.db.sql("""select name from `tabSerial No` where item_code='%s' 
		and ifnull(qty, 0) = 0
		and status='Available' and finished_good='No' and
		serial_no_warehouse='%s'"""%(doc['item_code'],doc['t_warehouse']),debug=1)
	elif doc['purpose']=='Sales Return':
		return frappe.db.sql("""select name from `tabSerial No` where item_code='%s'
		and status='Delivered'"""%(doc['item_code']))
	else:
		return frappe.db.sql("""select name from `tabSerial No` where item_code='%s'
		and ifnull(qty,0)<>0
		and status='Available' and serial_no_warehouse='%s'"""%(doc['item_code'],doc['s_warehouse'] or doc['t_warehouse']))

#anand
def get_serial_from(doctype,txt,searchfield,start,page_len,filters):
	return frappe.db.sql("""select name,item_name,status from `tabSerial No` 
		where item_code='%(item_code)s' 
		and ifnull(qc_status,'')=''
		and status='Available'"""%{'item_code':filters['item_code']})

def get_serial_from_psd(doctype,txt,searchfield,start,page_len,filters):
	return frappe.db.sql("""select name,item_name,status from `tabSerial No` 
		where item_code='%(item_code)s' 
		and ifnull(psd_status,'')=''
		and status='Available'"""%{'item_code':filters['item_code']})

def get_serial_from_sa(doctype,txt,searchfield,start,page_len,filters):
	return frappe.db.sql("""select name,item_name,status from `tabSerial No` 
		where item_code='%(item_code)s' 
		and ifnull(sa_analysis,'')=''
		and status='Available'"""%{'item_code':filters['item_code']})


def get_source_batch(doctype,txt,searchfield,start,page_len,filters):
	return frappe.db.sql("""select name from `tabBatch` 
		where warehouse='%s' 
		and name in(select name from `tabSerial No` 
			where qty!=0)"""%(filters.get('warehouse')))

#method called for purchase reciept is created 
def generate_serial_no(doc,method):
	
	for d in doc.get('purchase_receipt_details'):
		if not d.sr_no:
			frappe.throw(_("Select Serial No and Click on Add for Item: ").format(d.item_code))

		elif d.sr_no and d.qty_per_drum_bag:
			series=frappe.db.get_value('Serial No',{'name':d.custom_serial_no,'status':'Available','item_code':d.item_code},'naming_series')
			if series and d.qty_per_drum_bag:
				frappe.errprint([series, d.qty_per_drum_bag])
				frappe.db.sql("update `tabSerial No` set qty='%s',serial_no_warehouse='%s' where name='%s'"%(d.qty_per_drum_bag, d.warehouse,d.sr_no))
				qty=cint(d.qty) - cint(d.qty_per_drum_bag)
				serial_no_name=d.custom_serial_no + '\n'
				while cint(qty) > 0:
					qty_for_negative=cint(qty)
					qty = cint(qty) - cint(d.qty_per_drum_bag)
					if cint(qty) < 0:
						name=create_serial_no_pr(d,series,qty_for_negative)
					else:
						name=create_serial_no_pr(d,series,d.qty_per_drum_bag)
					serial_no_name+= name + '\n'
				frappe.db.sql("update `tabPurchase Receipt Item` set sr_no='%s' where parent='%s' and item_code='%s'"%(serial_no_name,doc.name,d.item_code))
				d.sr_no=serial_no_name
		elif d.sr_no and not d.qty_per_drum_bag:
			frappe.throw(_("Enter Quantity per Drum/Bag for Item {0}").format(d.item_code))

def create_serial_no_pr(d,series,qty):
	sr_no=frappe.new_doc('Serial No')
	sr_no.naming_series=series
	sr_no.item_code=d.item_code
	sr_no.qty=cstr(qty)
	sr_no.status="Available"
	sr_no.item_name=d.item_name
	sr_no.is_repacked='Yes'
	sr_no.serial_no_warehouse=d.warehouse
	sr_no.item_group=d.item_group
	sr_no.description=d.description
	sr_no.finished_good='No'
	sr_no.save(ignore_permissions=True)
	return sr_no.name



def delete_serial_no(doc,method):
		for d in doc.get('purchase_receipt_details'):
			if d.sr_no:
				sr_no=(d.sr_no).split('\n')
				for s in sr_no:
					frappe.db.sql("delete from `tabSerial No` where name='%s'"%(s))

def check_range(doc,method):
		parm=[]
		for d in doc.get("item_specification_details"):
			if d.min_value and d.max_value:
				if not flt(d.min_value) <= flt(d.max_value):
					msgprint(_("Min value should be less than max for Inspection parameters"),raise_exception=1)
			elif not d.min_value and not d.max_value:
				msgprint(_("Min and Max value can not be blank Inspection Parameter"),raise_exception=1)	
			if d.specification in parm:
				msgprint(_("Duplicate parameter {0} found at row {1}").format(d.specification,d.idx),raise_exception=1)
			parm.append(d.specification)	


@frappe.whitelist()
def make_quality_checking(mtn_details):
	mtn_details=eval(mtn_details)
	msg=''
	for d in mtn_details:
		if d.get('parenttype')=='Purchase Receipt' and d.get('sr_no'):
			serial_no = (d.get('sr_no')).splitlines() or (d.get('sr_no')).split('\n')
			msg=assign_checking(serial_no,d.get('item_code'))
		
		elif d.get('parenttype')=='Stock Entry' and d.get('custom_serial_no') and d.get('t_warehouse'):
			serial_no = (d.get('custom_serial_no')).splitlines() or (d.get('custom_serial_no')).split('\n')
			msg=assign_checking(serial_no,d.get('item_code'))
	if msg:
		frappe.msgprint(msg)

@frappe.whitelist()
def assign_checking(sr_no,item_code):
	msg='This serial no is already assigned'
	quality_checker=frappe.db.sql("select distinct parent from `tabUserRole` where role in('Quality Checker','System Manager')",as_list=1)
	if quality_checker:
		for checker in quality_checker:
			count = 0
			for s in sr_no:
				if not frappe.db.get_value('ToDo',{'serial_no':s,'owner':checker[0]},'name'):
					to_do=frappe.new_doc('ToDo')
					to_do.reference_type='Quality Checking'
					to_do.role='Quality Checker'
					to_do.owner=checker[0]
					to_do.assigned_by=frappe.session.user
					to_do.description='Do QC for Serial No %s'%(s)
					to_do.status='Open'
					to_do.priority='Medium'
					to_do.serial_no=s
					to_do.item_code=item_code
					to_do.save()
					count+=1
					if count!=0:
						msg="Assign {0} serial no to Quality Checker".format(count)
		return msg

