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
		if frappe.db.get_value('Item', d.item_code, 'serial_no') == 'Yes':
			if d.custom_serial_no and  d.qty_per_drum_bag and d.s_warehouse:
				sr_no=(d.custom_serial_no).splitlines()
				sr=''
				for s in sr_no:
					if s:
						if sr:
							sr+=','+'\''+s+'\''
						else:
							sr='\''+s+'\''
						sn_details = get_serial_NoInfo(s)
						check_qty_per_drum(d, d.qty_per_drum_bag, sn_details)
				qty=frappe.db.sql("""select SUM(qty) from `tabSerial No` 
					where name in (%s)"""%(sr),as_list=1)
				if qty:
					if flt(d.qty) > (qty[0][0]):
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

def update_stock_name(doc,method):
	if doc.purpose =='Repack' or doc.purpose=='Manufacture':
		for d in doc.get('mtn_details'):
			if d.s_warehouse and d.custom_serial_no:
				sr_no=(d.custom_serial_no).splitlines() or (d.custom_serial_no).split('\n')
				for sr in sr_no:
					append_ste(d,sr,doc)
					

def append_ste(d,serial_no,doc):
	bi =frappe.get_doc("Serial No", serial_no)
	ch = bi.append("serial_stock")
	ch.document=doc.name
	ch.item_code=d.item_code
	ch.serial_no=serial_no
	ch.qty=cstr(d.qty)
	ch.warehouse=d.t_warehouse
	ch.parent=serial_no
	ch.parentfield='serial_stock'
	ch.parenttype='Serial No'
	bi.save(ignore_permissions=True)
			

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
				frappe.throw(_("Please select serial no at row {0} for item code {1}").format(d.idx, d.item_code))


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
					frappe.throw(_("Drum {0} has been already delivered, please see row {1}").format(sr_no, d.idx))
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
	make_entry_for_sample_product(doc)
	for d in doc.get('delivery_note_details'):
		if d.custom_serial_no and d.sample_product == 'No':
			serial_no=(d.custom_serial_no).splitlines()
			delivery_note_qty = flt(d.qty)
			for sr_no in serial_no:
				if sr_no:
					if delivery_note_qty > 0:
						if flt(d.qty_per_drum_or_bag) > 0:
							sn_qty = flt(frappe.db.get_value('Serial No',sr_no,'qty'))
							if flt(sn_qty) >= flt(d.qty_per_drum_or_bag):
								qty = sn_qty - flt(d.qty_per_drum_or_bag)
							else:
								frappe.throw(_("Drum {0} has less qty, select proper drum").format(sr_no))
							delivery_note_qty = flt(delivery_note_qty) - flt(d.qty_per_drum_or_bag)
							make_serialgl_dn(d,sr_no, d.qty_per_drum_or_bag,doc)
							qty = 0 if qty < 1 else qty
							frappe.db.sql("update `tabSerial No` set qty=%s,status='Available' where name='%s'"%(qty , sr_no))
					else:
						frappe.throw(_("You have select extra drum at row {0}").format(d.idx))

def make_entry_for_sample_product(doc):
	obj = frappe.new_doc('Sample Product')
	obj.customer_name = doc.customer_name
	obj.delivery_note = doc.name
	status = 'No'
	for d in doc.delivery_note_details:
		if d.sample_product == 'Yes':
			status = 'Yes'
			make_sample_productdetails(obj, d)
	if status == 'Yes':
		obj.save(ignore_permissions=True)

def make_sample_productdetails(obj, args):
	spi = obj.append('sample_product_item', {})
	spi.item_code = args.item_code
	spi.no_of_drum = args.no_of_drum_or_bag
	spi.qty_per_drum = args.qty_per_drum_or_bag
	spi.total_qty = args.qty
	spi.drum_details = args.custom_serial_no

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
	delete_sample_product_entry(doc)
	for d in doc.get('delivery_note_details'):
		if d.custom_serial_no and d.sample_product == 'No':
			serial_no=(d.custom_serial_no).splitlines()
			for sr_no in serial_no:
				serial_no_qty=frappe.db.sql("select ifnull(qty,0) from `tabSerial Stock` where parent='%s' and document='%s'"%(sr_no,doc.name),as_list=1)
				if serial_no_qty:
					qty=qty+cint(serial_no_qty[0][0])
				amend_qty=frappe.db.get_value('Serial No',sr_no,'qty') or 0
				qty = qty + amend_qty
				frappe.db.sql("update `tabSerial No` set qty=%s,status='Available' where name='%s'"%(qty,sr_no))
				frappe.db.sql("delete from `tabSerial Stock` where parent='%s' and document='%s'"%(sr_no,doc.name))
				# frappe.db.sql("delete from `tabSerial No` where make_from='%s'"%(sr_no))

def delete_sample_product_entry(doc):
	name = frappe.db.get_value('Sample Product', {'delivery_note': doc.name}, 'name')
	if name:
		frappe.delete_doc('Sample Product', name)

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
				# validate_serial_no(d)
			
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
		validate_serial_no(d)

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
	update_charge_no(doc)
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
	create_serial_no_for_batch(d,previous_source_batch,doc,target_batch)
	# elif not previous_source_batch and not d.target_batch:
		# validate_serial_no(d)


def create_serial_no_for_batch(d,previous_source_batch,doc,target_batch):
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
	# frappe.db.commit()
	d.custom_serial_no=target_batch
	frappe.db.sql("update `tabStock Entry Detail` set custom_serial_no='%s',target_batch='%s' where parent='%s' and item_code='%s'"%(d.custom_serial_no,target_batch,doc.name,d.item_code))




def issue_serial_no(d,status,qty):
		if d.custom_serial_no:
			sr_no=(d.custom_serial_no).splitlines() or (d.custom_serial_no).split('\n')
			for s in sr_no:
				frappe.db.sql(""" update `tabSerial No` set status='%s',
					serial_no_warehouse='%s',qty=%s where name='%s'
					"""%(status, d.s_warehouse or d.t_warehouse, cint(qty), s))
		
				

#Update Serial Warehouse in serial no on material transfer
def update_serial_no_warehouse(doc,method):
	if doc.purpose=='Material Transfer'  :
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
						# frappe.db.commit()
						# make_serialgl(d,s,serial_qty,doc)
					elif qty > 0:
						frappe.db.sql("update `tabSerial No` set qty=qty-%s where name='%s'"%((cint(qty)),s))
						# frappe.db.commit()
						make_serialgl(d,s,qty,doc)
						qty= cint(qty) - cint(serial_qty)




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
	if doc.purpose in ['Manufacture']:
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
		if frappe.db.get_value('Item', d.item_code, 'serial_no') == 'Yes' and d.custom_serial_no and doc.purpose !='Material Transfer':
			if d.s_warehouse and not d.t_warehouse:
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
			elif d.t_warehouse and not d.s_warehouse:
				if d.custom_serial_no:
					serial_no_list = []
					serial_no=(d.custom_serial_no).split('\n')
					for sr_no in serial_no:
						if sr_no:
							serial_no_list.append(sr_no)
					if serial_no_list:
						serial_no_list.sort(reverse=True)
						for sr_no in serial_no_list:
							frappe.delete_doc("Serial No", sr_no)
					d.custom_serial_no = ''
		elif doc.purpose == 'Material Transfer':
			transfer_drum_warehouses(doc, d, d.s_warehouse)

#update batch status on use
def update_batch_status(status,target_batch):
	frappe.db.sql("""update `tabBatch` 
		set used='%s' where name='%s'"""%(status,target_batch))

def get_serial_no_dn(doctype,txt,searchfield,start,page_len,filters):
	doc=filters['doc']
	cond=get_conditions(doc)
	if cond:
		return frappe.db.sql("""select name, concat('QTY :',qty), concat('Grade : ',grade) from `tabSerial No` %s and status='Available' and ifnull(qty, 0) >0 and item_code='%s'
			and name like '%%%s%%' limit %s, %s """%(cond,doc['item_code'], txt, start, page_len)) or [['']]
	else:
		return [['']]

def get_conditions(doc):
	con=''
	qc=frappe.db.sql("""select chemical_analysis,psd_analysis,ssa from `tabItem` 
		where item_code='%s'"""%(doc['item_code']),as_list=1)
	if qc:
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
	if doc['t_warehouse'] and not doc['s_warehouse']:
		return [['']]
	else:
		warehouse = doc['s_warehouse'] or doc['t_warehouse']
		return frappe.db.sql("""select name, concat('Qty: ',round(qty,3)), concat('Grade :',grade) from `tabSerial No` where item_code='%s'
		and ifnull(qty,0)<>0
		and status='Available' and serial_no_warehouse='%s' and name like '%%%s%%' limit %s, %s"""%(doc['item_code'], warehouse, txt, start, page_len), debug=1)

#anand
def get_serial_from(doctype,txt,searchfield,start,page_len,filters):
	return frappe.db.sql("""select name,item_name,status from `tabSerial No` 
		where item_code='%s' 
		and ifnull(qc_status,'') <> 'Accepted'
		and status='Available' and item_code in(select name from tabItem where chemical_analysis='Yes')
		and name like '%%%s%%' limit %s, %s """%(filters['item_code'], txt, start, page_len))

def get_serial_from_psd(doctype,txt,searchfield,start,page_len,filters):
	return frappe.db.sql("""select name,item_name,status from `tabSerial No` 
		where item_code='%s' 
		and ifnull(psd_status,'')<>'Accepted'
		and status='Available' and 
		item_code in(select name from tabItem where psd_analysis='Yes')
		and name like '%%%s%%' limit %s, %s"""%(filters['item_code'], txt, start, page_len))

def get_serial_from_sa(doctype,txt,searchfield,start,page_len,filters):
	return frappe.db.sql("""select name,item_name,status from `tabSerial No` 
		where item_code='%s' 
		and ifnull(sa_analysis,'')<>'Accepted'
		and status='Available' and 
		item_code in(select name from tabItem where ssa='Yes')
		and name like '%%%s%%' limit %s, %s"""%(filters['item_code'], txt, start, page_len))


def get_source_batch(doctype,txt,searchfield,start,page_len,filters):
	return frappe.db.sql("""select name from `tabBatch` 
		where warehouse='%s' 
		and name in(select name from `tabSerial No` 
			where qty!=0)"""%(filters.get('warehouse')))

#method called for purchase reciept is created 
def generate_serial_no(doc,method):
	
	for d in doc.get('purchase_receipt_details'):
		# if not d.sr_no:
		# 	frappe.throw(_("Select Serial No and Click on Add for Item: ").format(d.item_code))

		if d.qty_per_drum_bag:
			create_serial_no_for_receipt(d)
			# series=frappe.db.get_value('Serial No',{'name':d.custom_serial_no,'status':'Available','item_code':d.item_code},'naming_series')
			# if series and d.qty_per_drum_bag:
			# 	frappe.db.sql("update `tabSerial No` set qty='%s',serial_no_warehouse='%s' where name='%s'"%(d.qty_per_drum_bag, d.warehouse,d.sr_no))
			# 	qty=cint(d.qty) - cint(d.qty_per_drum_bag)
			# 	serial_no_name=d.custom_serial_no + '\n'
			# 	while cint(qty) > 0:
			# 		qty_for_negative=cint(qty)
			# 		qty = cint(qty) - cint(d.qty_per_drum_bag)
			# 		if cint(qty) < 0:
			# 			name=create_serial_no_pr(d,series,qty_for_negative)
			# 		else:
			# 			name=create_serial_no_pr(d,series,d.qty_per_drum_bag)
			# 		serial_no_name+= name + '\n'
			# 	frappe.db.sql("update `tabPurchase Receipt Item` set sr_no='%s' where parent='%s' and item_code='%s'"%(serial_no_name,doc.name,d.item_code))
			# 	d.sr_no=serial_no_name
		elif not d.qty_per_drum_bag:
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
	inspection=frappe.db.sql("""select inspection_required 
		from `tabItem` where name='%s'"""%(item_code),as_dict=1)
	if inspection[0]['inspection_required']=='Yes':
		quality_tests=frappe.db.sql("""select chemical_analysis,psd_analysis, ssa 
			from `tabItem` where name='%s'"""%(item_code),as_dict=1)
		for test in quality_tests:
			if test['chemical_analysis']=='Yes':
				quality_checker=frappe.db.sql("""select distinct parent 
					from `tabUserRole` 
					where role in('Chemical Analyst','System Manager')""",as_list=1)
				if quality_checker:
					for checker in quality_checker:
						make_ToDo(sr_no,item_code,checker,'Chemical Analyst','Quality Checking')
			if test['psd_analysis']=='Yes':
				psd_checker=frappe.db.sql("""select distinct parent 
					from `tabUserRole`
					where role in('PSD Analyst','System Manager')""",as_list=1)
				if psd_checker:
					for psd in psd_checker:
						make_ToDo(sr_no,item_code,psd,'PSD Analyst','PSD Analysis')
			if test['ssa']=='Yes':
				ssa_checker=frappe.db.sql("""select distinct parent 
					from `tabUserRole` 
					where role in('SSA Analyst','System Manager')""",as_list=1)
				if ssa_checker:
					for ssa in ssa_checker:
						make_ToDo(sr_no,item_code,ssa,'SSA Analyst','Surface  Area Analysis')



def make_ToDo(sr_no,item_code,checker,role,reference_doc):
	count = 0
	for s in sr_no:
		if not frappe.db.get_value('ToDo',{'serial_no':s,'owner':checker[0],'reference_type':reference_doc},'name'):
			to_do=frappe.new_doc('ToDo')
			to_do.reference_type=reference_doc
			to_do.role=role
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
				msg="Assign {0} serial no to SSA Analyst".format(count)

# def update_serialNo_grade(serial_no):
# 	obj = frappe.get_doc('Serial No', serial_no)
# 	grade = 'R' if obj.qc_grade == 'R' or obj.psd_grade == 'R' else obj.qc_grade or obj.psd_grade
# 	grade = ('R' if obj.sa_grade == 'R' and grade == 'R' else '{0} - {1}'.format(grade, obj.sa_grade)) if obj.sa_grade and grade else obj.sa_grade or grade
# 	obj.grade = grade
# 	obj.save(ignore_permissions=True)

def update_serialNo_grade(serial_no):
	obj = frappe.get_doc('Serial No', serial_no)
	grades_list = [obj.qc_grade or '', obj.psd_grade or '', obj.sa_grade or '']
	grade = 'R' if 'R' in grades_list else ''.join(grades_list)
	obj.grade = grade
	obj.save(ignore_permissions=True)

def get_the_drums(doc, method):
	make_sicomill(doc)
	make_chargenumber_entries(doc)

def make_sicomill(doc):
	for d in doc.mtn_details:
		if frappe.db.get_value('Item', d.item_code, 'serial_no') == 'Yes' and doc.purpose != 'Material Transfer':
			if d.s_warehouse and not d.t_warehouse and d.qty_per_drum_bag:
				validate_serial_no(d)
				reduce_the_qty(doc, d)
			elif d.t_warehouse and not d.s_warehouse:
				create_serial_no(doc,d)
		elif doc.purpose == 'Material Transfer':
			validate_serial_no(d)
			transfer_drum_warehouses(doc, d, d.t_warehouse)

def reduce_the_qty(doc, args):
	if args.custom_serial_no:
		sn = cstr(args.custom_serial_no).split('\n')
		stock_entry_qty = args.qty
		for serial_no in sn:
			if serial_no:
				if flt(stock_entry_qty) > 0.0:
					sn_details = get_serial_NoInfo(serial_no)
					if flt(sn_details.qty) >= flt(args.qty_per_drum_bag):
						sn_details.qty = flt(sn_details.qty) - flt(args.qty_per_drum_bag)
						stock_entry_qty = stock_entry_qty - args.qty_per_drum_bag
					else:
						frappe.throw(_("Drum no {0} has less qty use another drum, check row {1}").format(serial_no, args.idx))
					make_serialgl(sn_details, args, serial_no , args.qty_per_drum_bag , doc)
				else:
					frappe.throw(_("You have select extra drum at row {0}").format(args	.idx))

def create_serial_no(doc, args):
	if args.no_of_qty and args.qty_per_drum_bag:
		serial = create_target_serial_no(args)
		args.custom_serial_no = '\n'.join(serial)

def get_serial_NoInfo(serial_no):
	return frappe.get_doc('Serial No', serial_no)

def create_target_serial_no(args):
	serial_no = []
	for r in range(0, cint(args.no_of_qty)):
		warehouse = args.t_warehouse or args.s_warehouse
		serial_name = custom_create_serial_no(args, warehouse,  args.grade, args.serial_no_uom, args.drum_or_bag_series)
		serial_no.append(serial_name)
	return serial_no

def custom_create_serial_no(args, warehouse, grade, serial_no_uom, naming_series):
	sn = frappe.new_doc('Serial No')
	sn.naming_series = naming_series
	sn.item_code = args.item_code
	sn.qty = args.qty_per_drum_bag
	sn.serial_no_warehouse = warehouse
	sn.item_name = args.item_name
	sn.description = args.description
	sn.purchase_document_type = args.parenttype
	sn.purchase_document_no = args.parent
	sn.type_of_container = serial_no_uom
	sn.grade = grade
	sn.purchase_date = nowdate()
	sn.save(ignore_permissions=True)
	return sn.name

def create_serial_no_for_receipt(args):
	serial_no = []
	count = flt(args.qty) / flt(args.qty_per_drum_bag)
	for r in range(0, cint(count)):
		warehouse = args.warehouse
		serial_name = custom_create_serial_no(args, warehouse, '', '', 'RM')
		serial_no.append(serial_name)
	args.sr_no = '\n'.join(serial_no)


# #keep track of serials used in stock entry
def make_serialgl(obj,d,serial_no,qty,doc):
	#change Serial Maintain to Serial Stock
	bi=obj.append('serial_stock',{})
	bi.document=doc.name
	bi.item_code=d.item_code
	bi.serial_no=serial_no
	bi.qty=cstr(qty)
	bi.warehouse=d.s_warehouse or d.t_warehouse
	# bi.parent=serial_no
	# bi.parentfield='serial_stock'
	# bi.parenttype='Serial No'
	obj.save(ignore_permissions=True)

def make_chargenumber_entries(doc):
	if doc.charge_number:
		charge_number = frappe.get_doc('Charge Number', doc.charge_number)
		process_charge_no(doc, charge_number)
		charge_number.save(ignore_permissions=True)

def process_charge_no(doc, obj):
	for d in doc.mtn_details:
		if d.s_warehouse and not d.t_warehouse:
			make_stock_in_entry(d, obj)
		elif d.t_warehouse and not d.s_warehouse:
			make_stock_out_entry(d, obj)

def make_stock_in_entry(args, obj):
	sti = obj.append('production_in_history', {})
	sti.stock_entry_number = args.parent
	sti.raw_material = args.item_code
	sti.in_qty = args.qty
	sti.in_warehouse = args.s_warehouse
	sti.drum_no_details = args.custom_serial_no


def make_stock_out_entry(args, obj):
	sti = obj.append('production_out_history', {})
	sti.stock_entry_number = args.parent
	sti.finished_goods = args.item_code
	sti.out_qty = args.qty
	sti.out_warehouse = args.t_warehouse
	sti.drum_no_details = args.custom_serial_no

def update_charge_no(doc):
	if doc.charge_number:
		frappe.db.sql(""" delete from `tabProduction History` where parent = '%s'
			and stock_entry_number = '%s'"""%(doc.charge_number, doc.name))
		frappe.db.sql(""" delete from `tabProduction Output History` where parent = '%s'
			and stock_entry_number = '%s'"""%(doc.charge_number, doc.name))

def check_qty_per_drum(args ,per_drum_qty, serial_no_details):
	if flt(per_drum_qty) > flt(serial_no_details.qty):
		frappe.throw(_("Row no {0}, drum no {1} has less qty inside, select another drum").format(args.idx, serial_no_details.name))

def transfer_drum_warehouses(doc, args, warehouse):
	if args.custom_serial_no:
		for sn in cstr(args.custom_serial_no).split('\n'):
			if sn:
				sn_details = get_serial_NoInfo(sn)
				sn_details.serial_no_warehouse = warehouse
				sn_details.save(ignore_permissions = True)