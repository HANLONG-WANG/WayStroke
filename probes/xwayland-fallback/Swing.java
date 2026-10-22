import javax.swing.*;
import java.nio.file.*;
import java.util.*;

// Disposable Swing fixture with the same file protocol as apps.py.
public class Swing {
    static String json(String s){StringBuilder b=new StringBuilder("\"");for(char c:s.toCharArray()){if(c=='"'||c=='\\')b.append('\\').append(c);else if(c<0x20||c>0x7e)b.append(String.format("\\u%04x",(int)c));else b.append(c);}return b.append('"').toString();}
    public static void main(String[] args) throws Exception {
        String name=args[0];Path root=Paths.get(System.getenv("WAYSTROKE_PROBE_DIR"));
        Path command=root.resolve(name+"-cmd.txt"),state=root.resolve(name+"-state.json"),temporary=root.resolve(name+"-state.tmp");
        SwingUtilities.invokeAndWait(()->{
            JFrame frame=new JFrame(name);JTextField normal=new JTextField(30);JPasswordField password=new JPasswordField(30);
            List<String> activated=new ArrayList<>();normal.addActionListener(e->activated.add(normal.getText()));
            JPanel panel=new JPanel();panel.setLayout(new BoxLayout(panel,BoxLayout.Y_AXIS));panel.add(normal);panel.add(password);
            frame.add(panel);frame.setSize(420,140);frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);frame.setVisible(true);
            Map<String,JTextField> fields=Map.of("normal",normal,"password",password);long[] seen={-1};
            new javax.swing.Timer(30,e->{try{
                if(Files.exists(command)){
                    Properties q=new Properties();try(var reader=Files.newBufferedReader(command)){q.load(reader);}
                    long seq=Long.parseLong(q.getProperty("seq"));
                    if(seq!=seen[0]){
                        seen[0]=seq;
                        for(var entry:fields.entrySet()){String value=q.getProperty("set."+entry.getKey());if(value!=null){entry.getValue().setText(new String(Base64.getDecoder().decode(value),"UTF-8"));entry.getValue().setCaretPosition(entry.getValue().getDocument().getLength());}}
                        String focus=q.getProperty("focus","");if(!focus.isEmpty())fields.get(focus).requestFocusInWindow();
                    }
                }
                String focus=normal.isFocusOwner()?json("normal"):password.isFocusOwner()?json("password"):"null";
                StringBuilder list=new StringBuilder("[");for(int i=0;i<activated.size();i++)list.append(i>0?",":"").append(json(activated.get(i)));list.append("]");
                Files.writeString(temporary,"{\"seq\":"+seen[0]+",\"normal\":"+json(normal.getText())+",\"password\":"+json(new String(password.getPassword()))+",\"focus\":"+focus+",\"activated\":"+list+",\"pid\":"+ProcessHandle.current().pid()+"}");
                Files.move(temporary,state,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
            }catch(Exception error){error.printStackTrace();}}).start();
        });
    }
}
