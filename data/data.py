"""
	Generic data handaling stuff
"""
from __future__ import annotations
from typing import TYPE_CHECKING
import csv
import logging
import sqlite3
from copy import deepcopy

if TYPE_CHECKING:
	from db.db import Database


def fix_width(the_str, width):
	if len(the_str) > width:
		ret = the_str[:width]
	else:
		ret = the_str.rjust(width, ' ')
	return ret


def exist_in_arr(name, arr, ignore_case=True):
	ret = False
	if ignore_case is False:
		ret = name in arr
	else:
		name = name.lower()
		for v in arr:
			if name.lower() == v:
				ret = True
				break

	return ret


class DataSet:
	"""
		utility class for spreadsheet style data

		poosble changes:
		the sqllite should be easy to mod to general sql methods just passing dbcon

	"""
	class Row:
		"""
			row data for example from __init__ is returned as Row object
			so that we can get data by col n or name 
		"""
		def __init__(self, data, head_map, ignore_head_case, alias):
			self._data = data
			self._head_map = head_map
			self._ignore_head_case = ignore_head_case
			self._alias = alias

		def _get_col_index(self, col):
			if type(col) is str:
				if self._ignore_head_case:
					col = col.lower()
				if col in self._alias:
					col = self._alias[col]
				else:
					col = self._head_map[col]
			return col

		def __getitem__(self, col):
			return self._data[self._get_col_index(col)]

		def __setitem__(self, col, value):
			self._data[self._get_col_index(col)] = value

		def __str__(self):
			return str(self._data)

	@classmethod
	def from_CSV(cls, fname, has_heads=True):
		"""
			return a dataset from given CSV file
			it's likely some cleanup/typing will be required after loading depending on what data is being used for
		"""

		logging.info('DataSet:from_CSV: %s' %fname)
		
		# attempt load Data
		with open(fname, newline='') as csvfile:
			my_reader = csv.reader(csvfile, delimiter=',', quotechar="'")

			# we'll use the first row as heads
			is_head = has_heads

			heads = None
			data = []
			
			for row in my_reader:
				if is_head:
					heads = row
				else:
					# where we have used 1st line as heads we'll guarantee that each row only has that much data
					if heads:
						data.append(row[:len(heads)])
					# the whole row gets added
					else:
						data.append(row)
				is_head=False
				
		return DataSet(heads, data)

	@classmethod
	def from_db(cls, db: Database, sql, args=[]):
		"""
		TODO: from_sqlite to be removed as this will replace and make it easier to switch databases
		creates a dataset from a query using our database helper - unlike from_CSV col data will be typed
		maybe for both methods which should allow caller to supply col/type mapping to change if required
		probably more important for csv though...
		"""
		return db.select_sql(sql, args)

	def __init__(self, heads=None, data=None, ignore_head_case=True):

		if data is None:
			data = []
		else:
			self._data = data

		if heads is None:
			# we'll just number based on first row, most likely you'll want to define your own later
			self._heads = []
			if data:
				for i in range(0, len(data[0])):
					self._heads.append(i)
		else:
			self._heads = heads

		self._ignore_head_case = ignore_head_case
		self._make_headmap()

		# cache of cols keyed on their vals
		# which will be
		# [col_n][col_val] = [rows that have this value, don't rely on the order]

		self._indexs = {}

		# using set alias cols can be accessed via another name
		self._alias = {}

	def create_sqlite_table(self, fname, tbl_name, col_attrs={}):
		"""
			creates a table tbl_name in database with heads of this DataSet
			by default all fields will be created as text.

			col_attrs can be used to modify what gets created as follows:

			col_attrs contains {
				# col name that this mod applies to
				col_name : {
					exclude : True,			# don't create this col
					type : int...			# create field as datatype
				}
			}

			col_names that don't exist will be added

		"""
		def _make_heads():
			"""
				makes the heads we're actually going to create by merging the DataSet Heads
				and col_attrs
			"""
			ret = []
			# heads from ds
			all_heads = self.Heads
			# add any new heads only defined in col_attrs
			for col_name in col_attrs:
				if col_name not in all_heads:
					all_heads.append(col_name)

			for col_name in all_heads:
				if col_name in col_attrs:
					attrs = col_attrs[col_name]
					# make sure col not being excluded
					if 'exclude' not in attrs or not attrs['exclude']:
						n_col = {
							'name': col_name,
							'type': 'text'
						}
						if 'type' in attrs:
							n_col['type'] = attrs['type']

						ret.append(n_col)

				else:
					ret.append({
						'name': col_name,
						'type': 'text'
					})

			return ret

		# generate the create sql
		sql_arr = ['create table %s (' % tbl_name]
		sep = ''

		for col in _make_heads():
			col_name = col['name']
			# default text
			col_type = 'text'

			# type defined in col_attrs
			if col_name in col_attrs:
				col_a = col_attrs[col_name]
				if 'type' in col_a:
					col_type = col_a['type']

			sql_arr.append('%s %s %s' % (sep, col['name'], col_type))
			sep = ', '
		sql_arr.append(')')
		sql = ''.join(sql_arr)

		# connect to db and execute sql
		logging.debug('DataSet::create_sqlite_table %s' % sql)
		with sqlite3.connect(fname) as con:
			con.execute(sql, [])

	@property
	def Heads(self):
		return self._heads

	@Heads.setter
	def Heads(self, n_heads):
		"""
			define our own heads this will ovewrite any that may have been set
			we pad with nums if heads sent in is not enough if we have cols in0 row of data
			which we use to infer that that col exits
		"""
		if self._data:
			self._heads = []
			for i in range(0,len(self._data[0])):
				if i<len(n_heads):
					self._heads.append(n_heads[i])
				else:
					self._heads.append(i)
		else:
			self._heads = n_heads

		# make the n to str mapping
		self._make_headmap()

	def _get_index(self, for_col):
		# get the actual n of the col even if given col_name
		col_i = self._get_col_index(for_col)
		# create if not already indexed
		if not col_i in self._indexs:
			self._indexs[col_i] = {}
			for c_row in self._data:
				if not c_row[col_i] in self._indexs[col_i]:
					self._indexs[col_i][c_row[col_i]] = []
				self._indexs[col_i][c_row[col_i]].append(c_row)

		return self._indexs[col_i]

	def set_alias(self, alias_name, for_col):
		"""
		:param alias_name: alt name for col
		:param for_col: n or name of col that will be reference by alias_name
		:return:
		"""
		self._alias[alias_name] = self._get_col_index(for_col)

	@property
	def Data(self):
		return self._data

	def has_head(self, the_head):
		if self._ignore_head_case is False:
			return the_head in self._heads
		else:
			return the_head.lower() in [h.lower() for h in self.Heads]

	def data_arr(self, for_cols):
		"""
			returns data in plain arr format
			if for_cols is a single head then it'll just be [a,b,c...] otherwise it'll be array of [[],[],[]...]
		"""
		ret = []
		the_head = None
		if isinstance(for_cols,str):
			the_head = for_cols
		elif len(for_cols)==1:
			the_head = for_cols[1]

		# only for single col
		if the_head:
			for c_row in self:
				ret.append(c_row[the_head])
		else:
			for c_row in self:
				n_row = []
				for c_head in for_cols:
					ret.append(n_row[the_head])
				ret.append(n_row)
		return ret

	def _make_headmap(self):
		# makes a lookup so we can ref data by col names
		self._head_map = {}
		for i,v in enumerate(self._heads):
			if self._ignore_head_case is True:
				v = v.lower()

			self._head_map[v] = i
			# so can also use col n
			self._head_map[i] = i

	def _col_data(self, row, head):
		# get the data in row for given head
		if isinstance(head,str) and self._ignore_head_case:
			head = head.lower()
		return row[self._head_map[head]]

	def _get_col_index(self, head):
		# returns the cols number
		if isinstance(head,str) and self._ignore_head_case:
			head = head.lower()
		return self._head_map[head]

	def unique(self, for_heads):
		"""
			returns a new dataset that is just the data for given heads
			where the data contains a row for each unique concat value of those heads
			if there are multiple rows where heads are the same you only get one
			order is retained
		"""
		matches = set()
		ret_data = []
		if isinstance(for_heads,str) or not hasattr(for_heads,'__iter__'):
			for_heads = [for_heads]
		
		for c_row in self._data:
			match_data = []
			for c_head in for_heads:
				match_data.append(self._col_data(c_row, c_head))
			
			match_str = ':'.join(match_data)
			if not match_str in matches:
				matches.add(match_str)
				ret_data.append(c_row.copy())
			
		return DataSet(self._heads.copy(), ret_data)
		
	def value_in(self, field, values, is_not=False):
		"""
			returns a data set of all rows where 
			field in values
			
			add flag for not in 
			for more advance stuff we'll write a subset where filter
			func can be given 
		"""
		if not hasattr(values,'__iter__') or isinstance(values, str):
			values = [values]
	
		ret_data = []

		col_n = self._get_col_index(field)
		
		for c_row in self._data:
			in_contained = c_row[col_n] in values
			
			# default add rows where value/s for field is in values
			if not is_not and in_contained:
				ret_data.append(c_row)
				
			# is_not has been set True which means we want all rows 
			# where value/s NOT contained in the field
			elif is_not and not in_contained:
				ret_data.append(c_row)

		return DataSet(self._heads.copy(), ret_data)
		
	def subset(self, filterFunc):
		"""
			returns a new dataset that contains only rows that pass filterFunc
		"""
		ret_data = []
		for c_row in self:
			if filterFunc(c_row):
				ret_data.append(c_row._data)
		
		return DataSet(self._heads.copy(), ret_data)

	def of_heads(self,the_heads):
		"""
			returns a dataset that only contains the cols given in the heads
		"""
		data = []

		for c_r in self:
			r_data = []
			for c_h in the_heads:
				r_data.append(c_r[c_h])
			data.append(r_data)

		return DataSet(the_heads, data)

	def matches(self, col, value):
		"""
			returns a new dataset that contains all rows where col=value
			because this uses the dict index it'll be quicker for multiple queries
			as the return is a dataset the exist can be chained to narrow down more
		"""
		idx = self._get_index(col)
		if value in idx:
			ret = DataSet(self._heads, idx[value])
		else:
			ret = DataSet(self.Heads, [])

		return ret

	def __iter__(self):
		for c_row_data in self._data:
			yield DataSet.Row(c_row_data, self._head_map, self._ignore_head_case, self._alias)
			
	def __getitem__(self, i):
		# row at i
		return DataSet.Row(self._data[i], self._head_map, self._ignore_head_case, self._alias)
			
	def __len__(self):
		return len(self._data)

	def extend(self, n_head, data_func):
		self._heads.append(n_head)
		# need to remap as heads updated
		self._make_headmap()
		
		for i,c_row in enumerate(self._data):
			c_row.append(data_func(DataSet.Row(c_row,self._head_map, self._ignore_head_case, self._alias)))

	def __copy__(self):
		return DataSet(deepcopy(self.Heads), deepcopy(self._data))

	def for_str_out(self, attrs={}, include_cols=None, include_heads=True, max_row=None, col_width=10):
		"""
		returns a string of the tbl aligned tabulated for easy printout

		:param attrs: extra data for cols keyed on col name
					col_name : {
						exclude : True		# col won't be output
						width: 5			# this width will be used rather than col_width
					}

		:param include_cols: output only these col names, def None will output all
		:param include_heads: output the col headers
		:param max_row: rows to print, None for all
		:param col_width: if not defined in attrbs the width of cols, extra text clipped
		:return:
		"""
		ret_arr = []

		# do the header row
		if include_heads:
			for c_head in self._heads:
				attr_exclude = False
				width = col_width

				# note that attrs don't correct for case so they need to map the actual col name value!
				if c_head in attrs:
					col_attrs = attrs[c_head]
					if 'width' in col_attrs:
						width = col_attrs['width']
					if 'exclude' in col_attrs:
						attr_exclude = col_attrs['exclude']

				# not exclude on attrb
				if not attr_exclude and (
						include_cols is None or exist_in_arr(c_head, include_cols, self._ignore_head_case)):
					ret_arr.append(fix_width(c_head, width))

		# and now the data rows
		for c_row in self:
			ret_arr.append('\n')
			for c_head in self._heads:
				attr_exclude = False
				width = col_width

				# note that attrs don't correct for case so they need to map the actual col name value!
				if c_head in attrs:
					col_attrs = attrs[c_head]
					if 'width' in col_attrs:
						width = col_attrs['width']
					if 'exclude' in col_attrs:
						attr_exclude = col_attrs['exclude']

				# not exclude on attrb
				if not attr_exclude and (
						include_cols is None or exist_in_arr(c_head, include_cols, self._ignore_head_case)):
					ret_arr.append(fix_width(str(c_row[c_head]), width))



		return ''.join(ret_arr)

	def __str__(self):
		return self.for_str_out()

	def as_arr(self, dict_rows=True):
		"""
			use this method if going to pass the contents as json
			default is [
				[heads,,], use to determine offset to access data
				[data,,,]
			]

			if dict_rows is true then
				[{
					col_name : data
				}]
			obvs this will be a lot larger

			NOTE there are no checks that the data in the cells is of a type that can be transferred as json

		"""
		ret = {
			'heads': self.Heads,
			'data': self.Data
		}
		if dict_rows:
			ret = []
			for c_r in self.Data:
				to_add = {}
				for c_h in self.Heads:
					to_add[c_h] = c_r[self._get_col_index(c_h)]
				ret.append(to_add)
		return ret

	def save_csv(self, filename, include_heads=True):
		if include_heads:
			to_output = [self._heads] + self._data
		else:
			to_output = self._data

		with open(filename, 'w', newline='\n') as csvfile:
			my_csv = csv.writer(csvfile, delimiter=',')
			my_csv.writerows(to_output)

