/*
Author: Billy Earney
Date: 04/19/2013
License: MIT

Description: This file can work as a "bridge" between nodejs and brython
 so that client side brython code can be executed on the server side.
Will brython replace Cython one day?  Only time will tell.
:)

*/

var fs = require('fs');

document={};
window={};
window.navigator={}
document.$py_src = {}
document.$debug = 0

self={};
__BRYTHON__={}
__BRYTHON__.$py_module_path = {}
__BRYTHON__.$py_module_alias = {}
__BRYTHON__.$py_next_hash = -Math.pow(2,53)
__BRYTHON__.exception_stack = []
__BRYTHON__.scope = {}
__BRYTHON__.modules = {}

// Read and eval library
// jscode = fs.readFileSync('../src/brython.js','utf8');
// eval(jscode);


var sources = [
'brython_builtins', 'version_info', 'py2js',
'py_object', 'py_type', 'py_utils', 'py_builtin_functions',
'py_exceptions', 'py_range_slice', 'py_bytes', 'js_objects',
'stdlib_paths', 'py_import', 'py_float', 'py_int', 'py_long_int',
'py_complex', 'py_list', 'py_string', 'py_dict', 'py_set', 'py_dom',
'py_generator', 'builtin_modules', 'py_import_hooks', 'async'
]

for(var __i=0;__i<sources.length;__i++) {
    require("../src/"+sources[__i]+".js");
}

//function node_import(module,alias,names) {
function $import_single(module) {
  var search_path=['../src/libs', '../src/Lib'];
  var ext=['.js', '.py'];
  var mods=[module, module+'/__init__'];

  for(var i=0, _len_i = search_path.length; i < _len_i; i++) {
     for (var j=0, _len_j = ext.length; j < _len_j; j++) {
         for (var k=0, _len_k = mods.length; k < _len_k; k++) {
             var path=search_path[i]+'/'+mods[k]+ext[j]

             //console.log("searching for " + path);
             var module_contents;
             try {
               module_contents=fs.readFileSync(path, 'utf8')
             } catch(err) {}
             if (module_contents !== undefined) {
                console.log("imported " + module)
                //console.log(module_contents);
                if (ext[j] == '.js') {
                   return $import_js_module(module,alias,names,path,module_contents)
                }
                return $import_py_module(module,alias,names,path,module_contents)
             }
         }
     }
  }
  console.log("error time!");
  res = Error()
  res.name = 'NotFoundError'
  res.message = "No module named '"+module+"'"
  throw res
}

$compile_python=function(module_contents,module) {
    var root = __BRYTHON__.py2js(module_contents,module,"__main__","__main__","__main__")
    var body = root.children
    root.children = []
    // use the module pattern : module name returns the results of an anonymous function
    var mod_node = new $Node('expression')
    //if(names!==undefined){alias='$module'}
    new $NodeJSCtx(mod_node,'$module=(function()')
    root.insert(0,mod_node)
    mod_node.children = body
    // search for module-level names : functions, classes and variables
    var mod_names = []
    for(var i=0, _len_i = mod_node.children.length; i < _len_i;i++){
        var node = mod_node.children[i]
        // use function get_ctx() 
        // because attribute 'context' is renamed by make_dist...
        var ctx = node.get_ctx().tree[0]
        if(ctx.type==='def'||ctx.type==='class'){
            if(mod_names.indexOf(ctx.name)===-1){mod_names.push(ctx.name)}
        } else if(ctx.type==='from') {
            for (var j=0, _len_j = ctx.names.length; j < _len_j; j++) {
                var name=ctx.names[j];
                if (name === '*') {
                   // just pass, we don't want to include '*'
                } else if (ctx.aliases[name] !== undefined) {
                   if (mod_names.indexOf(ctx.aliases[name])===-1){
                      mod_names.push(ctx.aliases[name])
                   }
                } else {
                   if (mod_names.indexOf(ctx.names[j])===-1){
                     mod_names.push(ctx.names[j])
                   }
                }
            }
        }else if(ctx.type==='assign'){
            var left = ctx.tree[0]
            if(left.type==='expr'&&left.tree[0].type==='id'&&left.tree[0].tree.length===0){
                var id_name = left.tree[0].value
                if(mod_names.indexOf(id_name)===-1){mod_names.push(id_name)}
            }
        }
    }
    // create the object that will be returned when the anonymous function is run
    var ret_code = 'return {'
    for(var i=0, _len_i = mod_names.length; i < _len_i;i++){
        ret_code += mod_names[i]+':'+mod_names[i]+','
    }
    ret_code += '__getattr__:function(attr){return this[attr]},'
    ret_code += '__setattr__:function(attr,value){this[attr]=value}'
    ret_code += '}'
    var ret_node = new $Node('expression')
    new $NodeJSCtx(ret_node,ret_code)
    mod_node.add(ret_node)
    // add parenthesis for anonymous function execution
    
    var ex_node = new $Node('expression')
    new $NodeJSCtx(ex_node,')()')
    root.add(ex_node)
    
    try{
        var js = root.to_js()
        return js;
    }catch(err){
        eval('throw '+err.name+'(err.message)')
    }
    return undefined;
}

function execute_python_script(filename) {
  _py_src=fs.readFileSync(filename, 'utf8')
  var fn = filename.split('/').pop()
  __BRYTHON__.$py_module_path['__main__']=filename
  var root = __BRYTHON__.py2js(_py_src,fn,fn,fn,fn)
  var js = root.to_js()
  console.log(js);
  eval(js);
}

//console.log("try to execute compile script");

__BRYTHON__.$py_module_path = __BRYTHON__.$py_module_path || {}
__BRYTHON__.$py_module_alias = __BRYTHON__.$py_module_alias || {}
__BRYTHON__.exception_stack = __BRYTHON__.exception_stack || []
__BRYTHON__.scope = __BRYTHON__.scope || {}
__BRYTHON__.imported = __BRYTHON__.imported || {}
__BRYTHON__.modules = __BRYTHON__.modules || {}
__BRYTHON__.compile_python=$compile_python
__BRYTHON__.meta_path = __BRYTHON__.meta_path || []
// __BRYTHON__.bound = __BRYTHON__.bound || {}
// __BRYTHON__.type = __BRYTHON__.type || {}
// __BRYTHON__.$py_src= __BRYTHON__.$py_src || {}

__BRYTHON__.debug = 0
__BRYTHON__.$options = {}
__BRYTHON__.$options.debug = 0


// other import algs don't work in node
//import_funcs=[node_import]

var filename=process.argv[2];
execute_python_script(filename)
